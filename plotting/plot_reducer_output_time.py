import json
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Read in json file of timestamps for map and reduce tasks
def get_json_input(fname):
    f = open(fname)
    data = json.load(f)
    map_times = []
    reduce_times = []
    for row in data:
        if row["name"] == "map":
            map_times.append(row["ts"])
        elif row["name"] == "reduce":
            reduce_times.append(row["ts"])
    return (map_times, reduce_times)


# https://scipy-cookbook.readthedocs.io/items/Matplotlib_LaTeX_Examples.html
fig_width_pt = 241.14749  # Get this from LaTeX using \showthe\columnwidth
inches_per_pt = 1.0 / 72.27  # Convert pt to inches
golden_ratio = (np.sqrt(5) - 1.0) / 2.0  # Aesthetic ratio
figwidth = fig_width_pt * inches_per_pt  # width in inches
figheight = figwidth * golden_ratio  # height in inches
figsize = (figwidth, figheight)
fontsize = 7

plt.rcParams.update(
    {
        "axes.titlesize": fontsize,
        "axes.labelsize": fontsize,
        "font.size": fontsize,
        "figure.figsize": figsize,
        "figure.dpi": 150,
        "legend.fontsize": fontsize,
        "text.usetex": True,
        "xtick.labelsize": fontsize,
        "ytick.labelsize": fontsize,
    }
)

sns.set_theme(style="ticks", font_scale=1)
sns.set_palette("Set2")


def get_data():
    output_time = [
        408.68507409095764,
        409.14794397354126,
        410.0801718235016,
        411.521142244339,
        412.46259236335754,
        413.147846698761,
        413.32224583625793,
        413.6786775588989,
        415.06468057632446,
        415.7010145187378,
        415.911758184433,
        416.9434177875519,
        417.52991914749146,
        418.0201802253723,
        418.2719750404358,
        418.57316732406616,
        419.302521944046,
        419.59510469436646,
        420.17970871925354,
        420.4062850475311,
        420.84526801109314,
        421.4981138706207,
        421.9361939430237,
        422.56056928634644,
        423.7068979740143,
        423.75542521476746,
        424.2186996936798,
        424.4611189365387,
        425.133394241333,
        425.6321702003479,
        425.6449284553528,
        426.74049711227417,
        427.4899353981018,
        427.5546305179596,
        428.4185025691986,
        429.21845722198486,
        429.2566440105438,
        429.4261405467987,
        430.06370425224304,
        431.7713623046875,
        432.52570819854736,
        432.6055676937103,
        432.8034768104553,
        432.8188350200653,
        433.30209517478943,
        434.2281446456909,
        434.5038068294525,
        436.3747978210449,
        436.45332980155945,
        436.5359237194061,
        437.21151757240295,
        437.4238841533661,
        437.87687635421753,
        438.6639530658722,
        438.8692512512207,
        439.9454801082611,
        440.6688508987427,
        441.3490607738495,
        441.43755173683167,
        441.4786043167114,
        441.507120847702,
        442.0028691291809,
        443.0472295284271,
        443.5828158855438,
        444.90668845176697,
        445.3439030647278,
        445.6562511920929,
        446.13035464286804,
        446.593120098114,
        447.09327149391174,
        447.14904713630676,
        447.7105920314789,
        449.00500869750977,
        449.4560561180115,
        449.45682525634766,
        450.21279430389404,
        450.6499135494232,
        450.8203094005585,
        451.96568775177,
        452.4518692493439,
        452.6275236606598,
        452.957896232605,
        453.8366892337799,
        454.0625801086426,
        454.1941382884979,
        455.5852518081665,
        456.76126289367676,
        457.25878643989563,
        457.41207551956177,
        457.66067600250244,
        457.76648926734924,
        458.1241207122803,
        459.0334620475769,
        460.7785437107086,
        461.1423659324646,
        461.2092344760895,
        461.74980306625366,
        461.7268691062927,
        462.63666915893555,
        462.8138930797577,
        462.9030656814575,
        464.74422669410706,
        465.0164382457733,
        465.2747061252594,
        465.5708963871002,
        466.25495982170105,
        467.9465494155884,
        467.95452666282654,
        468.00352120399475,
        468.3148145675659,
        469.7917969226837,
        470.00780153274536,
        470.34571170806885,
        471.3166079521179,
        471.7659640312195,
        471.9195964336395,
        472.48973870277405,
        473.05699825286865,
        473.9932520389557,
        474.4298017024994,
        474.7850592136383,
        475.2015495300293,
        476.10495138168335,
        476.8413496017456,
        477.2293152809143,
        477.9072940349579,
        477.93813371658325,
        478.10712242126465,
        478.7687041759491,
        479.96152663230896,
        481.3920180797577,
        482.13467288017273,
        482.1657030582428,
        482.35309958457947,
        483.0566463470459,
        483.18994784355164,
        483.83346676826477,
        485.19436144828796,
        485.8135619163513,
        486.32836842536926,
        487.0389549732208,
        487.5129978656769,
        487.52904176712036,
        488.07038402557373,
        489.0632629394531,
        489.092928647995,
        490.4296946525574,
        491.43886160850525,
        491.52042031288147,
        492.19667649269104,
        492.5635256767273,
        492.83186531066895,
        493.35592913627625,
        493.9246244430542,
        496.1182641983032,
        496.3799591064453,
        496.40862345695496,
        496.7849476337433,
        497.7468829154968,
        498.06739830970764,
        499.58482694625854,
        499.86302518844604,
        501.1906213760376,
        501.66306734085083,
        501.7333126068115,
        502.1943299770355,
        503.0316994190216,
        503.3304007053375,
        503.9615361690521,
        504.31149768829346,
        506.3877305984497,
        506.55290031433105,
        506.77292943000793,
        506.88721466064453,
        506.9190671443939,
        507.48368668556213,
        507.9866473674774,
        508.75291085243225,
        510.64213728904724,
        510.65083742141724,
        511.057359457016,
        511.832088470459,
        512.0014345645905,
        513.2543005943298,
        514.0084798336029,
        514.0153379440308,
        514.1184675693512,
        515.4938468933105,
        516.8639843463898,
        516.9990315437317,
        517.5701370239258,
        518.2256219387054,
        518.8569359779358,
        519.3105385303497,
        519.4949815273285,
        520.7053716182709,
        521.8094294071198,
        522.2794139385223,
        523.0650100708008,
        523.1281430721283,
        523.3618745803833,
        523.4398627281189,
        525.0844392776489,
        525.6308844089508,
        526.695476770401,
        527.4397151470184,
        527.5809352397919,
        528.2926027774811,
        528.3379595279694,
        528.3748841285706,
        530.3254597187042,
        530.6518268585205,
        531.8136649131775,
        531.8518810272217,
        532.3509979248047,
        532.714192867279,
        532.8916320800781,
        533.1324045658112,
        535.7351524829865,
        536.2360301017761,
        536.3682491779327,
        536.7215194702148,
        537.6834528446198,
        537.7374567985535,
        538.3763225078583,
        538.4021165370941,
        539.9357554912567,
        540.6184449195862,
        541.3431706428528,
        543.0491278171539,
        543.0916523933411,
        543.4783549308777,
        543.9981741905212,
        545.1519734859467,
        545.3682894706726,
        548.0022814273834,
        548.0800485610962,
        548.3927555084229,
        548.8846962451935,
        549.1067373752594,
        549.135448217392,
        550.3285820484161,
        551.9000818729401,
        553.1531586647034,
        553.466502904892,
        553.5835115909576,
        553.6157248020172,
        553.970333814621,
        557.1605279445648,
        557.5850427150726,
        557.5783922672272,
        558.7145459651947,
        562.5710911750793,
        564.1459875106812,
        567.801117181778,
        572.4551041126251,
    ]
    end_time = 580.817722
    num_reducers = len(output_time)
    data = [(i * 100 / num_reducers, t) for i, t in enumerate(output_time, start=1)]
    data.insert(0, (0, output_time[0] - 0.001))
    data.append((100, end_time))
    df = pd.DataFrame(data, columns=["pct", "time"])
    return df, 580.817722


def plot(df, end_time, figname, x="time", y="pct"):
    fig, ax = plt.subplots(figsize=figsize)
    g = sns.lineplot(data=df, x=x, y=y, ax=ax)
    plt.axvline(
        end_time,
        figure=fig,
        color="gray",
        linestyle="-",
        label="theoretical",
    )
    plt.fill_between(df[x].values, df[y].values, alpha=0.1)
    plt.xlim((0, 600))
    plt.ylim((0, 100))
    ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(decimals=0))
    plt.xlabel("Time (s)")
    plt.ylabel("Reducers completed")
    plt.grid(axis="y")
    filename = figname + ".pdf"
    print(filename)
    plt.savefig(filename, bbox_inches="tight")


df, end_time = get_data()
plot(df, end_time, "reducer_output_time")
