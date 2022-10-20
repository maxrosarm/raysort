# pylint: disable=too-many-instance-attributes,use-dict-literal
import math
import os
from dataclasses import InitVar, dataclass, field
from typing import Dict, List, Optional

import ray

from raysort.typing import AppStep, InstanceLifetime, SpillingMode

S3_BUCKET = os.getenv("S3_BUCKET")

CONFIG_NAME_ENV_VAR = "CONFIG"
APP_STEPS_ENV_VAR = "STEPS"

KiB = 1024
MiB = KiB * 1024
GiB = MiB * 1024
KB = 1000
MB = KB * 1000
GB = MB * 1000


def get_s3_buckets(count: int = 1) -> List[str]:
    assert S3_BUCKET
    return [f"{S3_BUCKET}-{i:03d}" for i in range(count)]


@dataclass
class InstanceType:
    name: str
    cpu: int
    memory_gib: float
    memory_bytes: int = field(init=False)
    disk_count: int = 0
    disk_device_offset: int = 1
    hdd: bool = False

    def __post_init__(self):
        self.memory_bytes = int(self.memory_gib * GiB)


@dataclass
class ClusterConfig:
    instance_count: int
    instance_type: InstanceType
    instance_lifetime: InstanceLifetime = InstanceLifetime.DEDICATED
    instance_disk_gb: int = 40
    ebs: bool = False
    local: bool = False
    name: str = ""

    def __post_init__(self):
        if self.ebs:
            self.instance_type.disk_count += 1
        if self.name == "":
            self.name = f"{self.instance_type.name}-{self.instance_count}"


@dataclass
class SystemConfig:
    _cluster: InitVar[ClusterConfig]
    max_fused_object_count: int = 2000
    object_spilling_threshold: float = 0.8
    # How much system memory to allocate for the object store.
    object_store_memory_percent: float = 0.6
    object_store_memory_bytes: int = field(init=False)
    # How much larger should /dev/shm be compared to the object store.
    shared_memory_multiplier: float = 1.001
    shared_memory_bytes: int = field(init=False)
    ray_storage: Optional[str] = f"s3://{S3_BUCKET}" if S3_BUCKET else None
    s3_spill: int = 0

    def __post_init__(self, cluster: ClusterConfig):
        self.object_store_memory_bytes = int(
            cluster.instance_type.memory_bytes * self.object_store_memory_percent
        )
        self.shared_memory_bytes = int(
            self.object_store_memory_bytes * self.shared_memory_multiplier
        )


@dataclass
class AppConfig:
    _cluster: InitVar[ClusterConfig]

    total_gb: float
    input_part_gb: float
    total_data_size: int = field(init=False)
    input_part_size: int = field(init=False)

    num_workers: int = field(init=False)
    num_mappers: int = field(init=False)
    num_shards_per_mapper: int = 1
    num_shards: int = field(init=False)
    input_shard_size: int = field(init=False)
    num_mappers_per_worker: int = field(init=False)
    num_mergers_per_worker: int = field(init=False)
    num_reducers: int = field(init=False)
    num_reducers_per_worker: int = field(init=False)

    num_concurrent_rounds: int = 2
    merge_factor: int = 2
    io_parallelism_multiplier: InitVar[float] = 2.0
    map_parallelism_multiplier: InitVar[float] = 0.5
    reduce_parallelism_multiplier: InitVar[float] = 0.5
    io_parallelism: int = field(init=False)
    map_parallelism: int = field(init=False)
    merge_parallelism: int = field(init=False)
    reduce_parallelism: int = field(init=False)

    io_size: int = 256 * KiB
    merge_io_parallelism: int = field(init=False)
    reduce_io_parallelism: int = field(init=False)

    skip_sorting: bool = False
    skip_input: bool = False
    skip_output: bool = False
    skip_first_stage: bool = False
    skip_final_reduce: bool = False

    spilling: SpillingMode = SpillingMode.RAY

    dataloader_mode: str = ""

    record_object_refs: bool = False

    native_scheduling: bool = False
    use_put: bool = False
    use_yield: bool = False

    simple_shuffle: bool = False
    riffle: bool = False
    magnet: bool = False

    s3_buckets: List[str] = field(default_factory=list)

    fail_node: Optional[str] = None
    fail_time: int = 45

    generate_input: bool = False
    sort: bool = False
    validate_output: bool = False

    # Runtime Context
    worker_ips: List[str] = field(default_factory=list)
    worker_ids: List[ray.NodeID] = field(default_factory=list)
    worker_ip_to_id: Dict[str, ray.NodeID] = field(default_factory=dict)
    data_dirs: List[str] = field(default_factory=list)
    is_local_cluster: bool = False

    def __post_init__(
        self,
        cluster: ClusterConfig,
        io_parallelism_multiplier: float,
        map_parallelism_multiplier: float,
        reduce_parallelism_multiplier: float,
    ):
        self.is_local_cluster = cluster.local
        self.total_data_size = int(self.total_gb * GB)
        self.input_part_size = int(self.input_part_gb * GB)
        self.io_parallelism = int(io_parallelism_multiplier * cluster.instance_type.cpu)
        self.map_parallelism = int(
            map_parallelism_multiplier * cluster.instance_type.cpu
        )
        self.reduce_parallelism = int(
            reduce_parallelism_multiplier * cluster.instance_type.cpu
        )

        self.num_workers = cluster.instance_count
        self.num_mappers = int(math.ceil(self.total_data_size / self.input_part_size))
        assert self.num_mappers % self.num_workers == 0, (
            self.num_mappers,
            self.num_workers,
        )
        self.num_shards = self.num_mappers * self.num_shards_per_mapper
        self.input_shard_size = self.input_part_size // self.num_shards_per_mapper
        self.num_mappers_per_worker = self.num_mappers // self.num_workers
        if self.riffle:
            assert self.merge_factor % self.map_parallelism == 0, (
                self.merge_factor,
                self.map_parallelism,
            )
            self.merge_parallelism = 1
        else:
            assert self.map_parallelism % self.merge_factor == 0, (
                self.map_parallelism,
                self.merge_factor,
            )
            self.merge_parallelism = self.map_parallelism // self.merge_factor
            self.merge_parallelism = self.map_parallelism // self.merge_factor
        if self.skip_first_stage:
            self.skip_input = True
        self.num_rounds = int(
            math.ceil(self.num_mappers / self.num_workers / self.map_parallelism)
        )
        self.num_mergers_per_worker = self.num_rounds * self.merge_parallelism
        self.num_reducers = self.num_mappers
        assert self.num_reducers % self.num_workers == 0, (
            self.num_reducers,
            self.num_workers,
        )
        self.num_reducers_per_worker = self.num_reducers // self.num_workers

        self.merge_io_parallelism = self.io_parallelism // self.merge_parallelism
        self.reduce_io_parallelism = self.io_parallelism // self.reduce_parallelism


@dataclass
class JobConfig:
    name: str
    cluster: ClusterConfig
    system: SystemConfig
    app: AppConfig

    def __init__(self, name: str, cluster: Dict, system: Dict, app: Dict):
        self.name = name
        self.cluster = ClusterConfig(**cluster)
        self.system = SystemConfig(**system, _cluster=self.cluster)
        self.app = AppConfig(**app, _cluster=self.cluster)


def get_steps(steps: Optional[List[AppStep]] = None) -> Dict:
    """
    Return a dictionary of steps to run for AppConfig.
    """
    if not steps:
        steps_str = os.getenv(APP_STEPS_ENV_VAR)
        if steps_str:
            steps = [AppStep(step) for step in steps_str.split(",")]
        if not steps:
            steps = [AppStep.GENERATE_INPUT, AppStep.SORT, AppStep.VALIDATE_OUTPUT]
    return {step.value: True for step in steps}


# ------------------------------------------------------------
#     VM Types
# ------------------------------------------------------------

d3_xl = InstanceType(
    name="d3.xlarge",
    cpu=4,
    memory_gib=32,
    disk_count=3,
    hdd=True,
)

d3_2xl = InstanceType(
    name="d3.2xlarge",
    cpu=8,
    memory_gib=61.8,
    disk_count=6,
    hdd=True,
)

i3_2xl = InstanceType(
    name="i3.2xlarge",
    cpu=8,
    memory_gib=61.8,
    disk_count=1,
    disk_device_offset=0,
)

i4i_2xl = InstanceType(
    name="i4i.2xlarge",
    cpu=8,
    memory_gib=61.8,
    disk_count=1,
)

i4i_4xl = InstanceType(
    name="i4i.4xlarge",
    cpu=16,
    memory_gib=123.6,
    disk_count=1,
)

i4i_8xl = InstanceType(
    name="i4i.8xlarge",
    cpu=32,
    memory_gib=247.2,
    disk_count=2,
)

r6i_2xl = InstanceType(
    name="r6i.2xlarge",
    cpu=8,
    memory_gib=61.8,
)

t3_2xl = InstanceType(
    name="t3.2xlarge",
    cpu=2,
    memory_gib=8,
    disk_device_offset=0,
)

m6i_xl = InstanceType(
    name="m6i.xlarge",
    cpu=4,
    memory_gib=16,
)


# ------------------------------------------------------------
#     Configurations
# ------------------------------------------------------------

local_cluster = dict(
    instance_count=min(os.cpu_count() or 16, 16),
    instance_type=InstanceType(
        name="local",
        cpu=2,
        memory_gib=0,  # not used
    ),
    local=True,
)

local_base_app_config = dict(
    **get_steps(),
    map_parallelism_multiplier=1,
    reduce_parallelism_multiplier=1,
)

local_mini_app_config = dict(
    **local_base_app_config,
    total_gb=0.16,
    input_part_gb=0.01,
)

local_app_config = dict(
    **local_base_app_config,
    total_gb=0.512,
    input_part_gb=0.002,
)


__configs__ = [
    # ------------------------------------------------------------
    #     Local experiments
    # ------------------------------------------------------------
    JobConfig(
        name="LocalSimple",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            simple_shuffle=True,
        ),
    ),
    JobConfig(
        name="LocalManualSpillingDisk",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            spilling=SpillingMode.DISK,
        ),
    ),
    JobConfig(
        name="LocalManualSpillingDiskParallel",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            spilling=SpillingMode.DISK,
        ),
    ),
    JobConfig(
        name="LocalNative",
        cluster=local_cluster,
        system=dict(),
        app=dict(**local_app_config),
    ),
    JobConfig(
        name="LocalNativePut",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            use_put=True,
        ),
    ),
    JobConfig(
        name="LocalNativeYield",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            use_yield=True,
        ),
    ),
    JobConfig(
        name="LocalMagnet",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            magnet=True,
        ),
    ),
    JobConfig(
        name="LocalRiffle",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            riffle=True,
            merge_factor=8,
        ),
    ),
    JobConfig(
        name="LocalNativeReduceOnly",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            skip_first_stage=True,
        ),
    ),
    JobConfig(
        name="LocalSchedulingDebug",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            simple_shuffle=True,
        ),
    ),
    # ------------------------------------------------------------
    #     Local fault tolerance experiments
    # ------------------------------------------------------------
    JobConfig(
        name="LocalSimpleFT",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            simple_shuffle=True,
            skip_input=True,
            fail_node=0,
        ),
    ),
    JobConfig(
        name="LocalNativeFT",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            skip_input=True,
            fail_node=0,
        ),
    ),
    JobConfig(
        name="LocalNativePutFT",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            use_put=True,
            skip_input=True,
            fail_node=0,
        ),
    ),
    JobConfig(
        name="LocalMagnetFT",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            magnet=True,
            skip_input=True,
            fail_node=0,
        ),
    ),
    JobConfig(
        name="LocalRiffleFT",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            riffle=True,
            merge_factor=8,
            skip_input=True,
            fail_node=0,
        ),
    ),
    # ------------------------------------------------------------
    #     Local S3 spilling experiments
    # ------------------------------------------------------------
    JobConfig(
        name="LocalS3Spilling",
        cluster=local_cluster,
        system=dict(
            s3_spill=4,
        ),
        app=dict(
            **local_mini_app_config,
        ),
    ),
    JobConfig(
        name="LocalS3IO",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_mini_app_config,
            s3_buckets=get_s3_buckets(),
        ),
    ),
    JobConfig(
        name="LocalS3IOMultiShard",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_mini_app_config,
            s3_buckets=get_s3_buckets(),
            num_shards_per_mapper=2,
        ),
    ),
    JobConfig(
        name="LocalS3IOAndSpilling",
        cluster=local_cluster,
        system=dict(
            s3_spill=4,
        ),
        app=dict(
            **local_mini_app_config,
            s3_buckets=get_s3_buckets(),
        ),
    ),
    JobConfig(
        name="LocalS3IOManualSpillingS3",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_mini_app_config,
            s3_buckets=get_s3_buckets(),
            spilling=SpillingMode.S3,
        ),
    ),
    JobConfig(
        name="LocalS3IOManualSpillingS3Parallel",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_mini_app_config,
            s3_buckets=get_s3_buckets(),
            spilling=SpillingMode.S3,
        ),
    ),
    # ------------------------------------------------------------
    #     t3.2xl 10 nodes scheduling policy debugging
    # ------------------------------------------------------------
    JobConfig(
        name="1tb-2gb-t3",
        cluster=dict(
            instance_count=10,
            instance_type=t3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
            map_parallelism_multiplier=1,
            reduce_parallelism_multiplier=1,
            native_scheduling=True,
        ),
    ),
    # ------------------------------------------------------------
    #     i3.2xl 10 nodes 1TB NSDI '23
    # ------------------------------------------------------------
    JobConfig(
        # 571s, https://wandb.ai/raysort/raysort/runs/2ib2wl1l
        name="1tb-2gb-i3-simple",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
            reduce_parallelism_multiplier=1,
            simple_shuffle=True,
        ),
    ),
    JobConfig(
        # 675s, https://wandb.ai/raysort/raysort/runs/15gi7d6y
        name="1tb-1gb-i3-simple",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=1,
            reduce_parallelism_multiplier=1,
            simple_shuffle=True,
        ),
    ),
    JobConfig(
        # 1038s, https://wandb.ai/raysort/raysort/runs/217qjb59
        name="1tb-.5gb-i3-simple",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=0.5,
            reduce_parallelism_multiplier=1,
            simple_shuffle=True,
        ),
    ),
    JobConfig(
        # 804s, https://wandb.ai/raysort/raysort/runs/2kuh08o8
        name="1tb-2gb-i3-riffle",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
            reduce_parallelism_multiplier=1,
            riffle=True,
            merge_factor=8,
        ),
    ),
    JobConfig(
        # 705s, https://wandb.ai/raysort/raysort/runs/16gj5var
        name="1tb-1gb-i3-riffle",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=1,
            reduce_parallelism_multiplier=1,
            riffle=True,
            merge_factor=8,
        ),
    ),
    JobConfig(
        # 770s, https://wandb.ai/raysort/raysort/runs/wp9zs9qb
        name="1tb-.5gb-i3-riffle",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=0.5,
            reduce_parallelism_multiplier=1,
            riffle=True,
            merge_factor=8,
        ),
    ),
    JobConfig(
        # 623s, https://wandb.ai/raysort/raysort/runs/1x8b6ggk
        name="1tb-2gb-i3-magnet",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
            reduce_parallelism_multiplier=1,
            magnet=True,
        ),
    ),
    JobConfig(
        # 608s, https://wandb.ai/raysort/raysort/runs/2qn6b7e7
        name="1tb-1gb-i3-magnet",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=1,
            reduce_parallelism_multiplier=1,
            magnet=True,
        ),
    ),
    JobConfig(
        # 630s, https://wandb.ai/raysort/raysort/runs/3c71pxms
        name="1tb-.5gb-i3-magnet",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=0.5,
            reduce_parallelism_multiplier=1,
            magnet=True,
        ),
    ),
    JobConfig(
        # 597s, https://wandb.ai/raysort/raysort/runs/2ot7wyr4
        name="1tb-2gb-i3-cosco",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
            reduce_parallelism_multiplier=1,
        ),
    ),
    JobConfig(
        # 612s, https://wandb.ai/raysort/raysort/runs/1fkhss8g
        name="1tb-1gb-i3-cosco",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=1,
            reduce_parallelism_multiplier=1,
        ),
    ),
    JobConfig(
        # 651s, https://wandb.ai/raysort/raysort/runs/1iatcdc6
        name="1tb-.5gb-i3-cosco",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=0.5,
            reduce_parallelism_multiplier=1,
        ),
    ),
    # ------------------------------------------------------------
    #     Local data loader experiments
    # ------------------------------------------------------------
    JobConfig(
        name="LocalNoStreamingDL",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            skip_input=True,
        ),
    ),
    JobConfig(
        name="LocalPartialStreamingDL",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            skip_input=True,
            dataloader_mode="partial",
        ),
    ),
    JobConfig(
        name="LocalFullStreamingDL",
        cluster=local_cluster,
        system=dict(),
        app=dict(
            **local_app_config,
            skip_input=True,
            dataloader_mode="streaming",
        ),
    ),
    # ------------------------------------------------------------
    #     d3.2xl 10 nodes 1TB (NSDI '22)
    # ------------------------------------------------------------
    JobConfig(
        # currently slow due to https://github.com/ray-project/ray/issues/24667
        name="1tb-2gb-d3-cosco",
        cluster=dict(
            instance_count=10,
            instance_type=d3_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
        ),
    ),
    # ------------------------------------------------------------
    #     i3.2xl 10 nodes 1TB (NSDI '22)
    # ------------------------------------------------------------
    JobConfig(
        # 584s, https://wandb.ai/raysort/raysort/runs/ky90ojwr
        name="1tb-2gb-i3-cosco",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
        ),
    ),
    # ------------------------------------------------------------
    #     i4i.2xl 10, 20 nodes
    # ------------------------------------------------------------
    JobConfig(
        # 361s, https://wandb.ai/raysort/raysort/runs/1hdz0pqi
        name="1tb-2gb-i4i",
        cluster=dict(
            instance_count=10,
            instance_type=i4i_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
            reduce_parallelism_multiplier=1,
        ),
    ),
    # ------------------------------------------------------------
    #     i4i.2xl 100 nodes
    # ------------------------------------------------------------
    JobConfig(
        # 607s, https://wandb.ai/raysort/raysort/runs/3b6bjy93
        # https://raysort.grafana.net/dashboard/snapshot/ODuYv9zKDbFnZc9GSS71mzyYC5MYdolK
        name="10tb-2gb-i4i",
        cluster=dict(
            instance_count=100,
            instance_type=i4i_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=10000,
            input_part_gb=2,
            reduce_parallelism_multiplier=1,
        ),
    ),
    JobConfig(
        # 3089s, https://wandb.ai/raysort/raysort/runs/35zd12xu
        # https://raysort.grafana.net/dashboard/snapshot/D47iMJ63Vl2eskBynzE472E17DhQqRs0
        name="50tb-2gb-i4i",
        cluster=dict(
            instance_count=100,
            instance_type=i4i_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=50000,
            input_part_gb=2,
            reduce_parallelism_multiplier=1,
        ),
    ),
    # ------------------------------------------------------------
    #     S3 + larger i4i nodes
    # ------------------------------------------------------------
    JobConfig(
        name="2tb-2gb-i4i4x-s3",
        cluster=dict(
            instance_count=10,
            instance_type=i4i_4xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=2000,
            input_part_gb=2,
            num_shards_per_mapper=4,
            s3_buckets=get_s3_buckets(),
            reduce_parallelism_multiplier=1,
            use_yield=True,
        ),
    ),
    # ------------------------------------------------------------
    #     S3 + i4i.2xl 10 nodes
    # ------------------------------------------------------------
    JobConfig(
        # 423s, https://wandb.ai/raysort/raysort/runs/p1ygq4c6
        name="1tb-2gb-i4i-native-s3",
        cluster=dict(
            instance_count=10,
            instance_type=i4i_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
            num_shards_per_mapper=4,
            s3_buckets=get_s3_buckets(),
            reduce_parallelism_multiplier=1,
            use_yield=True,
        ),
    ),
    # ------------------------------------------------------------
    #     S3 + i4i.2xl 20 nodes
    # ------------------------------------------------------------
    JobConfig(
        # 466s, https://wandb.ai/raysort/raysort/runs/jtrapg8i
        name="2tb-2gb-i4i-native-s3",
        cluster=dict(
            instance_count=20,
            instance_type=i4i_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=2000,
            input_part_gb=2,
            num_shards_per_mapper=4,
            s3_buckets=get_s3_buckets(2),
            reduce_parallelism_multiplier=1,
            use_yield=True,
        ),
    ),
    # ------------------------------------------------------------
    #     S3 + i4i.2xl 40 nodes
    # ------------------------------------------------------------
    JobConfig(
        # 536s, https://wandb.ai/raysort/raysort/runs/14xr10t2
        name="4tb-2gb-i4i-native-s3",
        cluster=dict(
            instance_count=40,
            instance_type=i4i_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=4000,
            input_part_gb=2,
            num_shards_per_mapper=4,
            s3_buckets=get_s3_buckets(4),
            reduce_parallelism_multiplier=1,
            use_yield=True,
        ),
    ),
    JobConfig(
        # 2901s, https://wandb.ai/raysort/raysort/runs/q0w17xxi
        name="20tb-2gb-i4i-native-s3",
        cluster=dict(
            instance_count=40,
            instance_type=i4i_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=20000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(4),
            reduce_parallelism_multiplier=1,
            use_yield=True,
        ),
    ),
    # ------------------------------------------------------------
    #     S3 + i4i.2xl 100 nodes
    # ------------------------------------------------------------
    JobConfig(
        # 681s, https://wandb.ai/raysort/raysort/runs/39gvukz0
        # 795s with multi upload
        name="10tb-2gb-i4i-native-s3",
        cluster=dict(
            instance_count=100,
            instance_type=i4i_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=10000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(10),
            reduce_parallelism_multiplier=1,
            use_yield=True,
        ),
    ),
    JobConfig(
        # 4153s, https://wandb.ai/raysort/raysort/runs/qcw9riog (multi upload)
        # https://raysort.grafana.net/dashboard/snapshot/41UCIyP11JsWOawGx3S0KMiyfmgBEjkt
        # 4028s, https://wandb.ai/raysort/raysort/runs/g03tgbgz (single upload)
        name="50tb-2gb-i4i-native-s3",
        cluster=dict(
            instance_count=100,
            instance_type=i4i_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=50000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(10),
            reduce_parallelism_multiplier=1,
        ),
    ),
    JobConfig(
        # TODO(@lsf)
        name="100tb-2gb-i4i-native-s3",
        cluster=dict(
            instance_count=100,
            instance_type=i4i_2xl,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=100000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(10),
            reduce_parallelism_multiplier=1,
        ),
    ),
    # ------------------------------------------------------------
    #     S3 10 nodes 1TB
    # ------------------------------------------------------------
    JobConfig(
        # 570s, https://wandb.ai/raysort/raysort/runs/2n652zza
        name="1tb-2gb-s3-native-s3",
        cluster=dict(
            instance_count=10,
            instance_type=r6i_2xl,
        ),
        system=dict(
            s3_spill=16,
        ),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(),
        ),
    ),
    JobConfig(
        # 575s, https://wandb.ai/raysort/raysort/runs/3vk1b0aa
        name="1tb-1gb-s3-native-s3",
        cluster=dict(
            instance_count=10,
            instance_type=r6i_2xl,
        ),
        system=dict(
            s3_spill=16,
        ),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=1,
            s3_buckets=get_s3_buckets(),
        ),
    ),
    JobConfig(
        # 650s, https://wandb.ai/raysort/raysort/runs/2d7d9ysa
        name="1tb-2gb-s3-manual-s3",
        cluster=dict(
            instance_count=10,
            instance_type=r6i_2xl,
        ),
        system=dict(
            object_spilling_threshold=1,
        ),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(),
            spilling=SpillingMode.S3,
            io_parallelism_multiplier=4,
        ),
    ),
    # ------------------------------------------------------------
    #     S3 20 nodes
    # ------------------------------------------------------------
    JobConfig(
        # 650s, https://wandb.ai/raysort/raysort/runs/30rszs7y
        # 580s, https://wandb.ai/raysort/raysort/runs/3e7h09lt (cannot reproduce)
        name="2tb-2gb-s3-native-s3",
        cluster=dict(
            instance_count=20,
            instance_type=r6i_2xl,
        ),
        system=dict(
            max_fused_object_count=3,
            s3_spill=16,
        ),
        app=dict(
            **get_steps(),
            total_gb=2000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(10),
            io_parallelism_multiplier=4,
        ),
    ),
    JobConfig(
        # 2906s, https://wandb.ai/raysort/raysort/runs/1r83qp4x
        name="10tb-2gb-s3-native-s3",
        cluster=dict(
            instance_count=20,
            instance_type=r6i_2xl,
        ),
        system=dict(
            max_fused_object_count=3,
            s3_spill=16,
        ),
        app=dict(
            **get_steps(),
            total_gb=10000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(),
        ),
    ),
    JobConfig(
        # 730s, https://wandb.ai/raysort/raysort/runs/2tlqlqpo
        name="2tb-2gb-s3-manual-s3",
        cluster=dict(
            instance_count=20,
            instance_type=r6i_2xl,
        ),
        system=dict(
            object_spilling_threshold=1,
        ),
        app=dict(
            **get_steps(),
            total_gb=2000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(),
            spilling=SpillingMode.S3,
            io_parallelism_multiplier=4,
        ),
    ),
    # ------------------------------------------------------------
    #     S3 40 nodes
    # ------------------------------------------------------------
    JobConfig(
        # 707s, https://wandb.ai/raysort/raysort/runs/2zekqq6m
        name="4tb-2gb-s3-manual-s3",
        cluster=dict(
            instance_count=40,
            instance_type=r6i_2xl,
        ),
        system=dict(
            object_spilling_threshold=1,
        ),
        app=dict(
            **get_steps(),
            total_gb=4000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(),
            spilling=SpillingMode.S3,
            io_parallelism_multiplier=4,
        ),
    ),
    JobConfig(
        # TODO(@lsf)
        name="20tb-2gb-s3-manual-s3",
        cluster=dict(
            instance_count=40,
            instance_type=r6i_2xl,
        ),
        system=dict(
            object_spilling_threshold=1,
        ),
        app=dict(
            **get_steps(),
            total_gb=20000,
            input_part_gb=2,
            s3_buckets=get_s3_buckets(),
            spilling=SpillingMode.S3,
            io_parallelism_multiplier=4,
        ),
    ),
    # ------------------------------------------------------------
    #     Spot instances 20 nodes
    # ------------------------------------------------------------
    JobConfig(
        name="600gb-1gb-spot-s3",
        cluster=dict(
            instance_count=20,
            instance_type=r6i_2xl,
            instance_lifetime=InstanceLifetime.SPOT,
        ),
        system=dict(
            max_fused_object_count=3,
            s3_spill=16,
        ),
        app=dict(
            **get_steps(),
            total_gb=600,
            input_part_gb=1,
            s3_buckets=get_s3_buckets(),
        ),
    ),
    # ------------------------------------------------------------
    #     Spot version of i3.2xl 10 nodes 1TB
    # ------------------------------------------------------------
    JobConfig(
        # 584s, https://wandb.ai/raysort/raysort/runs/ky90ojwr
        name="1tb-2gb-i3-spot",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            instance_lifetime=InstanceLifetime.SPOT,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=1000,
            input_part_gb=2,
        ),
    ),
    # ------------------------------------------------------------
    #     MapReduce Online Test Cluster
    # ------------------------------------------------------------
    JobConfig(
        name="mpo",
        cluster=dict(
            instance_count=8,
            instance_type=r6i_2xl,
            instance_lifetime=InstanceLifetime.SPOT,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=64,
            input_part_gb=1,
        ),
    ),
    # ------------------------------------------------------------
    #     Ad Hoc Experiments
    # ------------------------------------------------------------
    JobConfig(
        name="i3-simple",
        cluster=dict(
            instance_count=10,
            instance_type=i3_2xl,
            local=False,
        ),
        system=dict(),
        app=dict(
            **get_steps(),
            total_gb=100,
            input_part_gb=1.25,
            use_yield=True,
            reduce_parallelism_multiplier=1,
            # simple
            simple_shuffle=True,
            map_parallelism_multiplier=1,
        ),
    ),
]
__config_dict__ = {cfg.name: cfg for cfg in __configs__}


def get(config_name: Optional[str] = None) -> JobConfig:
    if config_name is None:
        config_name = os.getenv(CONFIG_NAME_ENV_VAR)
    assert config_name, f"No configuration specified, please set ${CONFIG_NAME_ENV_VAR}"
    assert config_name in __config_dict__, f"Unknown configuration: {config_name}"
    return __config_dict__[config_name]
