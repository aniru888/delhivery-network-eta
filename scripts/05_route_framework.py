"""P4 step 5: FTL vs Carting decision framework (profile-level, per A1).

Registered design (analysis-design.md section 9 A1, supersedes section 6):
  - Exact-corridor overlap is 14 training corridors / 574 legs - too thin.
    It appears here ONLY as a corroborating exhibit.
  - Profile cells: osrm_distance training-tercile x dispatch window
    (06-18 day / 18-06 night) x intra/inter-state = 12 cells (L0).
  - Support gate: a cell enters with >=30 training legs of EACH route type.
    Pre-stated merge order for failing cells: collapse dispatch window first
    (L1: tercile x intra = 6 cells), then distance terciles to halves
    (L2: half x intra = 4 cells). Still unsupported -> NO recommendation.
  - Within-cell observational comparison (training legs): median delay ratio
    (primary - normalizes distance) + median absolute minutes (secondary).
    Caveat carried everywhere: route type is CHOSEN, not assigned; selection
    on unobservables is possible. No causal language.
  - Counterfactual: M3 (re-fit, same seed/hypers as step 4) scores TEST legs
    in supported cells with route_type flipped; median predicted delta
    reported per cell. Zero recommendations outside supported cells (gate).
  - Break-even: cost constants are DIALS (no cost data exists):
    C_F = FTL cost per trip, c_c = Carting cost per kg, v = value of one
    minute of delay per shipment. Measured input = within-cell time delta.
    V* = (C_F - v * dt_minutes) / c_c, dt = median(Carting - FTL) minutes.

Run:  python scripts/05_route_framework.py   (from the project folder)
Outputs: outputs/route_framework.csv, outputs/route_framework.png + stdout.
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
CLEAN = os.path.join(PROJ, "data", "clean")
OUT = os.path.join(PROJ, "outputs")

SEED = 42
HP3 = dict(learning_rate=0.1, max_depth=8, max_iter=200)  # step-4 selection
MIN_N = 30

# cost dials (NO cost data in the dataset - these are stated assumptions)
C_F = 18000.0   # INR per FTL trip [dial]
C_C = 9.0       # INR per kg, Carting [dial]
V_MIN = 2.0     # INR per minute of delay per shipment [dial]

legs = pd.read_csv(os.path.join(CLEAN, "legs.csv"))
legs["ratio"] = legs["actual_time"] / legs["osrm_time"]
train = legs[legs["data"] == "training"].copy()
test = legs[legs["data"] == "test"].copy()
assert len(train) == 18948, "split drifted"

# ------------------------------------------------------------- profile cells
terc = train["osrm_distance"].quantile([1 / 3, 2 / 3]).to_numpy()
half = train["osrm_distance"].quantile([0.5]).to_numpy()
print(f"[cells] distance terciles at {terc[0]:.1f} / {terc[1]:.1f} km "
      f"(training); half split at {half[0]:.1f} km")


def cell_cols(frame):
    f = frame.copy()
    f["dist3"] = np.select(
        [f["osrm_distance"] <= terc[0], f["osrm_distance"] <= terc[1]],
        ["short", "mid"], "long")
    f["dist2"] = np.where(f["osrm_distance"] <= half[0], "shorter", "longer")
    f["window"] = np.where(f["dispatch_hour"].between(6, 17), "day", "night")
    f["scope"] = np.where(f["source_state"] == f["dest_state"], "intra", "inter")
    f["L0"] = f["dist3"] + "|" + f["window"] + "|" + f["scope"]
    f["L1"] = f["dist3"] + "|" + f["scope"]
    f["L2"] = f["dist2"] + "|" + f["scope"]
    return f


train = cell_cols(train)
test = cell_cols(test)


def supported(frame, col):
    p = frame.pivot_table(index=col, columns="route_type", values="ratio",
                          aggfunc="size").fillna(0)
    for rt in ("FTL", "Carting"):
        if rt not in p:
            p[rt] = 0
    return set(p[(p["FTL"] >= MIN_N) & (p["Carting"] >= MIN_N)].index)


sup0 = supported(train, "L0")
rest1 = train[~train["L0"].isin(sup0)]
sup1 = supported(rest1, "L1")
rest2 = rest1[~rest1["L1"].isin(sup1)]
sup2 = supported(rest2, "L2")
unsupported = rest2[~rest2["L2"].isin(sup2)]


def resolve(frame):
    lvl = np.select([frame["L0"].isin(sup0), frame["L1"].isin(sup1),
                     frame["L2"].isin(sup2)],
                    ["L0:" + frame["L0"], "L1:" + frame["L1"],
                     "L2:" + frame["L2"]], default="UNSUPPORTED")
    return lvl


train["cell"] = resolve(train)
test["cell"] = resolve(test)

# GATE: supported-cell table published BEFORE any comparison
print(f"\n[gate] support resolution (>= {MIN_N} training legs per route type):")
print(f"  L0 cells passing: {len(sup0)} of 12 | L1 rescues: {len(sup1)} "
      f"| L2 rescues: {len(sup2)}")
tbl = (train[train["cell"] != "UNSUPPORTED"]
       .pivot_table(index="cell", columns="route_type", values="ratio",
                    aggfunc="size").fillna(0).astype(int))
print(tbl.to_string())
n_unsup = (train["cell"] == "UNSUPPORTED").sum()
print(f"  UNSUPPORTED training legs (no recommendation): {n_unsup} "
      f"({n_unsup / len(train) * 100:.1f}%)")

# --------------------------------------- within-cell observational comparison
rows = []
for cell, g in train[train["cell"] != "UNSUPPORTED"].groupby("cell"):
    ftl = g[g["route_type"] == "FTL"]
    crt = g[g["route_type"] == "Carting"]
    rows.append(dict(
        cell=cell, n_ftl=len(ftl), n_carting=len(crt),
        ratio_ftl=ftl["ratio"].median(), ratio_carting=crt["ratio"].median(),
        min_ftl=ftl["actual_time"].median(), min_carting=crt["actual_time"].median(),
        dt_raw_min=crt["actual_time"].median() - ftl["actual_time"].median(),
        osrm_med=g["osrm_time"].median(),
        # distance-held-fixed delta: ratio gap x the cell's typical OSRM time.
        # Raw minutes are confounded even within cells (FTL runs longer km
        # within the same tercile); the ratio normalizes by construction.
        dt_star_min=(crt["ratio"].median() - ftl["ratio"].median())
                    * g["osrm_time"].median()))
cmp_df = pd.DataFrame(rows).sort_values("cell")
print("\n[compare] within-cell medians (training; observational - route type "
      "is chosen, not assigned):")
print(cmp_df.round(2).to_string(index=False))

# ------------------------------------------------- counterfactual M3 scoring
# rebuild step-4 M3 features (train-only artifacts), re-fit with step-4 hypers
import importlib.util
spec = importlib.util.spec_from_file_location(
    "m4", os.path.join(HERE, "04_model.py"))
# NOTE: importing 04_model would re-run the whole contest; instead re-implement
# the minimal feature path here by re-using its artifact builders via exec of
# the function definitions is overkill - simplest correct path: rebuild the
# SAME features with the same code inline (kept in sync by the step-7 cold
# re-run gate, which executes both scripts and reconciles outputs).
import networkx as nx

CORRIDOR = ["source_center", "destination_center"]


def corridor_artifacts(frame):
    g = frame.groupby(CORRIDOR)
    a = g.agg(corr_n=("ratio", "size"), corr_median_ratio=("ratio", "median"),
              corr_median_actual=("actual_time", "median")).reset_index()
    rt = (frame.groupby(CORRIDOR + ["route_type"]).size().rename("n")
          .reset_index().sort_values("n", ascending=False).drop_duplicates(CORRIDOR))
    a = a.merge(rt[CORRIDOR + ["route_type"]].rename(
        columns={"route_type": "major_rt"}), on=CORRIDOR, how="left")
    kappa = float(a["corr_n"].median())
    rt_med = frame.groupby("route_type")["ratio"].median()
    prior = a["major_rt"].map(rt_med)
    a["corr_shrunk_ratio"] = ((a["corr_n"] * a["corr_median_ratio"] + kappa * prior)
                              / (a["corr_n"] + kappa))
    return a.drop(columns=["major_rt"]), rt_med


def node_artifacts(frame):
    src = frame.groupby("source_center")["ratio"].agg(["mean", "median", "size"])
    src.columns = ["nsrc_mean_ratio", "nsrc_median_ratio", "nsrc_n"]
    dst = frame.groupby("destination_center")["ratio"].agg(["mean", "median", "size"])
    dst.columns = ["ndst_mean_ratio", "ndst_median_ratio", "ndst_n"]
    corr = frame.groupby(CORRIDOR).agg(median_actual=("actual_time", "median"),
                                       median_ratio=("ratio", "median")).reset_index()
    G = nx.DiGraph()
    for r in corr.itertuples(index=False):
        G.add_edge(r[0], r[1], median_actual=float(r.median_actual))
    btw = nx.betweenness_centrality(G, weight="median_actual", normalized=True)
    clust = nx.clustering(G)
    seq = frame.sort_values(["trip_uuid", "od_start_time"])
    thr = {}
    for _, gg in seq.groupby("trip_uuid", sort=False):
        d = gg["destination_center"].tolist()
        s = gg["source_center"].tolist()
        for k in range(len(gg) - 1):
            if d[k] == s[k + 1]:
                thr[d[k]] = thr.get(d[k], 0) + 1
    dwell = (frame["od_duration_min"] - frame["actual_time"]).groupby(
        frame["source_center"]).median()
    nodes = pd.DataFrame(index=sorted(set(G.nodes())))
    nodes["betweenness"] = pd.Series(btw)
    nodes["clustering"] = pd.Series(clust)
    nodes["in_degree"] = pd.Series(dict(G.in_degree()))
    nodes["out_degree"] = pd.Series(dict(G.out_degree()))
    nodes["throughput"] = pd.Series(thr).reindex(nodes.index).fillna(0)
    nodes["dwell_median"] = dwell.reindex(nodes.index)
    inc_sum, inc_cnt = {}, {}
    for r in corr.itertuples(index=False):
        for v in (r[0], r[1]):
            inc_sum[v] = inc_sum.get(v, 0.0) + float(r.median_ratio)
            inc_cnt[v] = inc_cnt.get(v, 0) + 1
    nodes["inc_ratio_sum"] = pd.Series(inc_sum)
    nodes["inc_ratio_cnt"] = pd.Series(inc_cnt)
    return src, dst, nodes, corr.set_index(CORRIDOR)["median_ratio"]


def build_features(frame, corr_art, src, dst, nodes, corr_ratio, emb):
    X = frame[["osrm_time", "osrm_distance", "dispatch_hour", "dispatch_dow"]].copy()
    for c in ["route_type", "source_state", "dest_state"]:
        X[c] = frame[c].fillna("unknown").astype("category")
    X = X.join(frame[CORRIDOR].merge(corr_art, on=CORRIDOR, how="left")
               [["corr_n", "corr_shrunk_ratio", "corr_median_actual"]]
               .set_index(frame.index))
    X = X.join(src.reindex(frame["source_center"]).set_index(frame.index))
    X = X.join(dst.reindex(frame["destination_center"]).set_index(frame.index))
    sn = nodes.reindex(frame["source_center"]).set_index(frame.index)
    dn = nodes.reindex(frame["destination_center"]).set_index(frame.index)
    own = corr_ratio.reindex(pd.MultiIndex.from_frame(frame[CORRIDOR])).to_numpy()
    for tag, nd in [("s", sn), ("d", dn)]:
        for c in ["betweenness", "clustering", "in_degree", "out_degree",
                  "throughput", "dwell_median"]:
            X[f"{tag}_{c}"] = nd[c].to_numpy()
        s_sum = nd["inc_ratio_sum"].to_numpy()
        s_cnt = nd["inc_ratio_cnt"].to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            excl = np.where(~np.isnan(own) & (s_cnt > 1),
                            (s_sum - own) / (s_cnt - 1), s_sum / s_cnt)
        X[f"{tag}_nbr_ratio_excl"] = excl
    se = emb.reindex(frame["source_center"]).set_index(frame.index)
    de = emb.reindex(frame["destination_center"]).set_index(frame.index)
    return X.join(se.add_prefix("s_")).join(de.add_prefix("d_"))


corr_art, rt_med = corridor_artifacts(train)
src_a, dst_a, node_a, corr_ratio = node_artifacts(train)
emb = pd.read_csv(os.path.join(CLEAN, "emb_train.csv")).set_index("center")

X_train = build_features(train, corr_art, src_a, dst_a, node_a, corr_ratio, emb)
m3 = HistGradientBoostingRegressor(loss="absolute_error",
                                   categorical_features="from_dtype",
                                   random_state=SEED, **HP3)
m3.fit(X_train, train["actual_time"].to_numpy())

sup_test = test[test["cell"] != "UNSUPPORTED"].copy()
X_t = build_features(sup_test, corr_art, src_a, dst_a, node_a, corr_ratio, emb)
flipped = sup_test.copy()
flipped["route_type"] = np.where(sup_test["route_type"] == "FTL",
                                 "Carting", "FTL")
X_f = build_features(flipped, corr_art, src_a, dst_a, node_a, corr_ratio, emb)
pred_as_is = m3.predict(X_t)
pred_flip = m3.predict(X_f)
# delta oriented as predicted(Carting) - predicted(FTL) for every leg
delta_cf = np.where(sup_test["route_type"] == "FTL",
                    pred_flip - pred_as_is, pred_as_is - pred_flip)
sup_test["cf_carting_minus_ftl"] = delta_cf
cf = (sup_test.groupby("cell")["cf_carting_minus_ftl"]
      .agg(["median", "size"]).rename(
          columns={"median": "cf_dt_min", "size": "n_test_legs"}))
print("\n[counterfactual] M3 predicted Carting-minus-FTL minutes per supported "
      "cell (test legs, model counterfactual - inherits observational limits):")
print(cf.round(1).to_string())
if cf["cf_dt_min"].abs().max() < 1.0:
    print("[counterfactual] VERDICT: deltas ~0 everywhere - M3 treats route "
          "type as informationally redundant given corridor/node history, so "
          "it CANNOT serve as a counterfactual instrument. Reported as a "
          "finding; the framework's time input is the observational "
          "within-cell ratio gap (dt_star), not the model.")

# ------------------------------------------------------------- break-even
frame = cmp_df.merge(cf, left_on="cell", right_index=True, how="left")
frame["breakeven_kg"] = (C_F - V_MIN * frame["dt_star_min"]) / C_C
print(f"\n[break-even] dials: FTL Rs.{C_F:,.0f}/trip, Carting Rs.{C_C}/kg, "
      f"delay value Rs.{V_MIN}/min [ALL ASSUMED - no cost data in dataset]")
print("  V* = (C_F - v*dt_star)/c_c -> ship FTL above V* kg, Carting below"
      " (dt_star = distance-held-fixed delta; dt_raw shown for contrast):")
print(frame[["cell", "dt_raw_min", "dt_star_min", "cf_dt_min", "breakeven_kg"]]
      .round(1).to_string(index=False))

# -------------------------------------- exact-corridor corroborating exhibit
both = (train.groupby(CORRIDOR)["route_type"].nunique() > 1)
both_corr = both[both].index
ex = train.set_index(CORRIDOR).loc[both_corr].reset_index()
piv = ex.pivot_table(index=CORRIDOR, columns="route_type", values="ratio",
                     aggfunc="median")
piv = piv.dropna()
ftl_faster = (piv["FTL"] < piv["Carting"]).sum()
print(f"\n[exhibit] exact-corridor overlap: {len(piv)} training corridors with "
      f"both types; FTL has lower median ratio on {ftl_faster} of {len(piv)} "
      f"(corroborating exhibit only - 574 legs total, registered as too thin)")

# ------------------------------------------------------------------- chart
plot = cmp_df.sort_values("cell").reset_index(drop=True)
fig, ax = plt.subplots(figsize=(9, 5.5))
y = np.arange(len(plot))
ax.scatter(plot["ratio_carting"], y, color="#c0392b", label="Carting", zorder=3)
ax.scatter(plot["ratio_ftl"], y, color="#1a4a72", label="FTL", zorder=3)
for i, r in plot.iterrows():
    ax.plot([r["ratio_ftl"], r["ratio_carting"]], [i, i], color="#999", lw=1.2)
ax.set_yticks(y)
ax.set_yticklabels(plot["cell"], fontsize=9)
ax.set_xlabel("median delay ratio (actual / OSRM), training")
worse = (plot["ratio_carting"] > plot["ratio_ftl"]).sum()
ax.set_title(f"Carting runs a worse delay ratio than FTL in {worse} of "
             f"{len(plot)} supported profiles", fontsize=12)
ax.legend()
ax.grid(alpha=0.3, axis="x")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "route_framework.png"), dpi=160)
plt.close(fig)

frame.to_csv(os.path.join(OUT, "route_framework.csv"), index=False)
print(f"\n[saved] outputs/route_framework.csv ({len(frame)} cells), "
      f"outputs/route_framework.png")
print(f"[seeds] SEED={SEED}, HP3={HP3}")
