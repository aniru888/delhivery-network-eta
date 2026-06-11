"""P4 Network Ops Console - Streamlit dashboard (brief checklist item 6).

Run from the project folder:
    streamlit run app/network_console.py

Design system: ~/.claude/design-systems/custom/delhivery-network-ops.md
(PostHog-warm, sibling of the P3 console). Every figure traces to
data/clean/*.csv or outputs/*.csv - no invented numbers. Model vocabulary
(MAE, bootstrap) appears only inside the Evidence tab.
"""

import os

import numpy as np
import pandas as pd
import streamlit as st

APP = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(APP)
CLEAN = os.path.join(PROJ, "data", "clean")
OUT = os.path.join(PROJ, "outputs")

# design tokens (delhivery-network-ops.md)
INK, INK_STRONG, MUTED = "#4d4f46", "#23251d", "#9ea096"
RISK, RISK_SOFT, OK, NAVY = "#B91C1C", "#F3DDDA", "#3F6C42", "#0f2a4a"

PROMISE_CAL = 2.0   # network median actual/OSRM ratio, training (step-3 log)

st.set_page_config(page_title="Network Ops Console", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', system-ui, sans-serif; }
.kpi { border-top: 1px solid #bfc1b7; padding: 12px 4px 4px 4px; }
.kpi .num { font-size: 30px; font-weight: 700; color: #23251d; letter-spacing: -0.5px; }
.kpi .lab { font-size: 13px; font-weight: 600; color: #4d4f46;
            text-transform: uppercase; letter-spacing: 0.4px; }
.kpi .sub { font-size: 12px; color: #9ea096; }
.prov { font-size: 12px; color: #9ea096; }
.quote-num { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; }
h1, h2, h3 { color: #23251d; }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load():
    legs = pd.read_csv(os.path.join(CLEAN, "legs.csv"))
    legs["ratio"] = legs["actual_time"] / legs["osrm_time"]
    train = legs[legs["data"] == "training"].copy()
    chronic = pd.read_csv(os.path.join(OUT, "chronic_corridors.csv"))
    hubs = pd.read_csv(os.path.join(OUT, "hub_ranking.csv"))
    comp = pd.read_csv(os.path.join(OUT, "model_comparison.csv"))
    preds = pd.read_csv(os.path.join(OUT, "test_predictions.csv"))
    agg = pd.read_csv(os.path.join(CLEAN, "corridor_agg.csv"))
    names = (pd.concat([
        legs.rename(columns={"source_center": "c", "source_name": "n"})[["c", "n"]],
        legs.rename(columns={"destination_center": "c", "destination_name": "n"})[["c", "n"]]])
        .dropna().drop_duplicates("c").set_index("c")["n"])
    return train, chronic, hubs, comp, preds, agg, names


train, chronic, hubs, comp, preds, agg, names = load()


def short(code):
    return str(names.get(code, code)).split(" (")[0]


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### Promise settings")
    level = st.radio("Promise level", ["Median (p50)", "Safe (p80)", "Safer (p90)"],
                     index=1,
                     help="Which percentile of historical corridor times to quote. "
                          "p80 was kept 78% of the time on the held-out week.")
    margin = st.slider("Breach margin (x promised)", 1.0, 1.5, 1.2, 0.05,
                       help="A leg counts as late when actual time exceeds "
                            "promised x margin. The level is a policy dial; "
                            "rankings barely move with it.")
    rt_filter = st.multiselect("Route type", ["FTL", "Carting"],
                               default=["FTL", "Carting"])
    st.markdown('<p class="prov">Calibration window: Sep 12-26, 2018.<br>'
                'Held-out check: Sep 27 - Oct 3.<br>'
                'Numbers regenerate from scripts 01-05.</p>',
                unsafe_allow_html=True)

Q = {"Median (p50)": 0.5, "Safe (p80)": 0.8, "Safer (p90)": 0.9}[level]

tview = train[train["route_type"].isin(rt_filter)] if rt_filter else train
promised = tview["osrm_time"] * PROMISE_CAL
late = tview["actual_time"] > promised * margin
excess_hours_day = (tview["actual_time"] - tview["osrm_time"]).sum() / 60 / 15
chron_view = chronic[chronic["major_route_type"].isin(rt_filter)] if rt_filter else chronic

# ---------------------------------------------------------------- verdict
st.markdown("## Network Ops Console")
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f'<div class="kpi"><div class="num">{excess_hours_day:,.0f} h</div>'
            f'<div class="lab">Hours lost vs routing estimate, per day</div>'
            f'<div class="sub">actual minus OSRM, {len(tview):,} legs / 15 days</div></div>',
            unsafe_allow_html=True)
c2.markdown(f'<div class="kpi"><div class="num">{late.sum() / 15:,.0f}</div>'
            f'<div class="lab">Late legs per day at this margin</div>'
            f'<div class="sub">{late.mean() * 100:.1f}% of legs; margin x{margin:.2f}</div></div>',
            unsafe_allow_html=True)
c3.markdown(f'<div class="kpi"><div class="num">{len(chron_view)}</div>'
            f'<div class="lab">Chronically delayed corridors</div>'
            f'<div class="sub">worst decile, min 5 runs; median one breaches every run</div></div>',
            unsafe_allow_html=True)
c4.markdown(f'<div class="kpi"><div class="num">3</div>'
            f'<div class="lab">Bottleneck hubs, statistically solid</div>'
            f'<div class="sub">survive 98-100% of resampling; ranks 4-6 are a tie</div></div>',
            unsafe_allow_html=True)

tab_n, tab_h, tab_q, tab_e = st.tabs(
    ["Network", "Hubs", "Quote an ETA", "Evidence"])

# ---------------------------------------------------------------- network
with tab_n:
    left, right = st.columns([3, 2])
    with left:
        st.image(os.path.join(OUT, "bottleneck_map.png"),
                 caption="Training-period network. Navy = top-5 hubs by excess "
                         "minutes; red = chronic corridors.")
    with right:
        st.markdown("### Worst corridors by delay risk")
        show = chron_view.copy()
        show["corridor"] = show["source_short"] + " > " + show["dest_short"]
        show["late_runs"] = (show["breached_legs"].astype(int).astype(str)
                             + " of " + show["legs_total"].astype(int).astype(str))
        st.dataframe(
            show[["corridor", "major_route_type", "shrunk_ratio", "late_runs"]]
            .rename(columns={"major_route_type": "type",
                             "shrunk_ratio": "delay risk"})
            .sort_values("delay risk", ascending=False),
            hide_index=True, height=430,
            column_config={
                "delay risk": st.column_config.ProgressColumn(
                    "delay risk (x OSRM)", min_value=0,
                    max_value=float(show["shrunk_ratio"].max()),
                    format="%.2f"),
            })
        st.markdown('<p class="prov">Delay risk = corridor\'s typical actual-vs-'
                    'OSRM multiple, shrunk toward its route-type norm so thin '
                    'corridors cannot top the list. 93% of chronic corridors '
                    'are intra-state; 68% are Carting.</p>',
                    unsafe_allow_html=True)

# ------------------------------------------------------------------- hubs
with tab_h:
    st.markdown("### Where the hours die")
    h = hubs.head(12).copy()
    h["hub"] = h["name"].str.split(" (", regex=False).str[0]
    h["excess_h_day"] = h["excess_min_total"] / 60 / 15
    st.dataframe(
        h[["hub", "excess_h_day", "breached_legs", "dwell_gap_median_min",
           "throughput_trips", "betweenness_time_cost"]]
        .rename(columns={"excess_h_day": "hours lost /day",
                         "breached_legs": "late legs (15d)",
                         "dwell_gap_median_min": "median dwell (min)",
                         "throughput_trips": "through-trips",
                         "betweenness_time_cost": "map centrality"}),
        hide_index=True, height=320,
        column_config={
            "hours lost /day": st.column_config.ProgressColumn(
                "hours lost /day", min_value=0,
                max_value=float(h["excess_h_day"].max()), format="%.0f"),
            "map centrality": st.column_config.NumberColumn(format="%.3f"),
        })
    st.markdown('<p class="prov">Hours count both endpoints of a leg - valid '
                'for ranking, not additive across hubs. Ranks 4-6 swap under '
                'resampling; treat them as one watch-tier.</p>',
                unsafe_allow_html=True)
    d1, d2, d3 = st.columns(3)
    d1.markdown("**Gurgaon Bilaspur HB** - pass-through chokepoint. Most "
                "through-traffic in the network (86 chained trips). Fix: "
                "sortation/cross-dock capacity, parallel routing for "
                "non-terminating trips.")
    d2.markdown("**Bhiwandi Mankoli HB** - volume terminal, almost no "
                "through-traffic (7). Most late legs in the network (399). "
                "Fix: dock scheduling and unload capacity, not routing.")
    d3.markdown("**Bangalore Nelmangala H** - mixed profile. 2.4 h median "
                "dwell is the binding constraint. Fix: dwell reduction first.")

# ------------------------------------------------------------------ quote
with tab_q:
    st.markdown("### Quote an ETA")
    eligible = agg[agg["corr_n"] >= 5].copy() if "corr_n" in agg else agg[agg["n_legs"] >= 5].copy()
    ncol = "corr_n" if "corr_n" in eligible.columns else "n_legs"
    eligible["label"] = (eligible["source_center"].map(short) + "  >  "
                         + eligible["destination_center"].map(short))
    eligible = eligible.sort_values(ncol, ascending=False)
    pick = st.selectbox("Corridor", eligible["label"].tolist(), index=0)
    row = eligible[eligible["label"] == pick].iloc[0]
    cl = train[(train["source_center"] == row["source_center"])
               & (train["destination_center"] == row["destination_center"])]
    osrm_med = float(cl["osrm_time"].median())
    if len(cl) >= 10:
        q_ratio = float(cl["ratio"].quantile(Q))
        basis = f"this corridor's own {len(cl)} runs"
    else:
        rt = cl["route_type"].mode().iloc[0]
        q_ratio = float(train.loc[train["route_type"] == rt, "ratio"].quantile(Q))
        basis = f"route-type history ({rt}) - corridor has only {len(cl)} runs"
    cal = float(cl["ratio"].median()) * osrm_med
    promise = q_ratio * osrm_med
    a, b, c = st.columns(3)
    a.markdown(f'<div class="kpi"><div class="num" style="color:{MUTED}">'
               f'{osrm_med:.0f} min</div>'
               f'<div class="lab">Routing engine says</div>'
               f'<div class="sub">drive time only - kept ~5% of the time '
               f'network-wide</div></div>', unsafe_allow_html=True)
    b.markdown(f'<div class="kpi"><div class="num">{cal:.0f} min</div>'
               f'<div class="lab">Realistic estimate</div>'
               f'<div class="sub">typical actual time on this corridor</div></div>',
               unsafe_allow_html=True)
    c.markdown(f'<div class="kpi"><div class="num" style="color:{OK}">'
               f'{promise:.0f} min</div>'
               f'<div class="lab">Quote at {level.split(" ")[0].lower()} '
               f'{level.split(" ")[1]}</div>'
               f'<div class="sub">basis: {basis}</div></div>',
               unsafe_allow_html=True)
    cov80 = float((preds["actual_time"] <= preds["q80"]).mean())
    cov90 = float((preds["actual_time"] <= preds["q90"]).mean())
    st.markdown(f'<p class="prov">Held-out week check, network-wide: p80 quotes '
                f'were kept {cov80 * 100:.0f}% of the time, p90 quotes '
                f'{cov90 * 100:.0f}%. A quote is "kept" when the shipment '
                f'arrives within the quoted time.</p>', unsafe_allow_html=True)

# --------------------------------------------------------------- evidence
with tab_e:
    st.markdown("### Model contest (held-out week, touched once)")
    ev = comp.copy()
    ev["model"] = ev["model"].map({
        "M0_osrm": "OSRM as-is (incumbent)",
        "M1_lookup": "Corridor calibration table",
        "M2_tabular": "Strong tabular model",
        "M3_graph": "+ graph features",
        "M3_LEAKY_fullgraph": "Graph features WITH leak (what most teams ship)",
    }).fillna(ev["model"])
    st.dataframe(ev[["model", "leg_MAE", "leg_w15", "trip_MAE", "cold_MAE"]]
                 .rename(columns={"leg_MAE": "avg error (min)",
                                  "leg_w15": "within 15%",
                                  "trip_MAE": "trip-level error",
                                  "cold_MAE": "new-corridor error"}),
                 hide_index=True,
                 column_config={
                     "within 15%": st.column_config.NumberColumn(format="percent"),
                     "avg error (min)": st.column_config.NumberColumn(format="%.1f"),
                     "trip-level error": st.column_config.NumberColumn(format="%.1f"),
                     "new-corridor error": st.column_config.NumberColumn(format="%.1f"),
                 })
    st.markdown(
        "**The two findings.** (1) Graph features add nothing once a facility's "
        "own history is in the model: the pre-registered test (bootstrap CI of "
        "the M2-M3 error difference) includes zero, overall and on new "
        "corridors. (2) Computing graph features on the full dataset - "
        "ignoring the time split - flatters the error by 27%. Teams claiming "
        "a big graph advantage on this dataset are measuring their own leak.")
    e1, e2 = st.columns(2)
    e1.image(os.path.join(OUT, "sla_sensitivity.png"),
             caption="The breach rate is a policy dial: 49% to 16% across margins.")
    e2.image(os.path.join(OUT, "route_framework.png"),
             caption="FTL runs a better delay ratio in 9 of 10 profiles "
                     "(observational - route type is chosen, not assigned).")
    st.markdown('<p class="prov">Scope: 22 non-peak days (Sep-Oct 2018). '
                'Festival-season bottlenecks are unmeasured and will be worse. '
                'SLA figures use a constructed promise (no SLA column exists in '
                'the data); rankings are robust to the dial, absolute rates are '
                'not.</p>', unsafe_allow_html=True)
