"""P4 step 4: model contest M0-M3, leak experiment, quantile ETAs.

Protocol (analysis-design.md sections 2-3, amendments section 9):
  M0  OSRM as-is (the incumbent).
  M1  corridor lookup: train shrunk ratio x osrm_time, route-type fallback.
  M2  strong tabular HGB + node-level train aggregates (A2).
  M3  M2 + STRUCTURAL-only graph features: centralities, dwell, degrees,
      neighbor-excluding-own-corridor delay aggregate, node2vec embeddings.
  Leak experiment: M3 refit with FULL-data artifacts (corridor aggregates,
      node aggregates, structural metrics, embeddings all computed on
      train+test legs) - the contaminated variant everyone else ships.
  A3: graph advantage demonstrable iff 95% corridor-cluster-bootstrap CI of
      MAE(M2)-MAE(M3) excludes zero (overall AND cold-start separately).
      Trip ground truth = sum of leg transit times.
  Quantiles: p50/p80/p90 HGB (loss="quantile") on M3 features.

Model selection: temporal sub-split inside training (trips created Sep 12-23
fit, Sep 24-26 validation), small registered grid, selected by val MAE.
Test (Sep 27-Oct 3) touched once per final model. Seeds fixed (A5): 42.

Known limitation (logged): aggregate features include the own leg for
TRAINING rows (no leave-one-out); test features use train-only aggregates,
so test metrics are uncontaminated - the cost is training overtrust only.

sklearn API verified via Context7 this session: categorical_features=
"from_dtype", loss="absolute_error"/"quantile" (+ quantile param).

Run:  python scripts/04_model.py   (from the project folder)
Outputs: outputs/model_comparison.csv, outputs/test_predictions.csv
"""

import os

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
CLEAN = os.path.join(PROJ, "data", "clean")
OUT = os.path.join(PROJ, "outputs")
os.makedirs(OUT, exist_ok=True)

SEED = 42
B = 1000
CORRIDOR = ["source_center", "destination_center"]

legs = pd.read_csv(os.path.join(CLEAN, "legs.csv"))
legs["ratio"] = legs["actual_time"] / legs["osrm_time"]
train_all = legs[legs["data"] == "training"].copy()
test = legs[legs["data"] == "test"].copy()
assert len(train_all) == 18948 and len(test) == 7421, "split drifted"


# ---------------------------------------------------------- artifact builders
def corridor_artifacts(frame):
    """Corridor aggregates with A4 shrinkage, computed on `frame` legs."""
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
    return a.drop(columns=["major_rt"]), rt_med, kappa


def node_artifacts(frame):
    """A2 node-level aggregates + A5 structural metrics, computed on `frame`."""
    src = frame.groupby("source_center")["ratio"].agg(["mean", "median", "size"])
    src.columns = ["nsrc_mean_ratio", "nsrc_median_ratio", "nsrc_n"]
    dst = frame.groupby("destination_center")["ratio"].agg(["mean", "median", "size"])
    dst.columns = ["ndst_mean_ratio", "ndst_median_ratio", "ndst_n"]

    corr = frame.groupby(CORRIDOR).agg(median_actual=("actual_time", "median"),
                                       median_ratio=("ratio", "median"),
                                       n=("ratio", "size")).reset_index()
    G = nx.DiGraph()
    for r in corr.itertuples(index=False):
        G.add_edge(r[0], r[1], median_actual=float(r.median_actual))
    btw = nx.betweenness_centrality(G, weight="median_actual", normalized=True)
    clust = nx.clustering(G)
    deg_in = dict(G.in_degree())
    deg_out = dict(G.out_degree())

    # observed throughput (chained intermediate stops)
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
    nodes["in_degree"] = pd.Series(deg_in)
    nodes["out_degree"] = pd.Series(deg_out)
    nodes["throughput"] = pd.Series(thr).reindex(nodes.index).fillna(0)
    nodes["dwell_median"] = dwell.reindex(nodes.index)

    # neighbor delay aggregate per node (incident-corridor mean raw median
    # ratio); per-leg own-corridor exclusion happens in build_features
    inc_sum, inc_cnt = {}, {}
    for r in corr.itertuples(index=False):
        for v in (r[0], r[1]):
            inc_sum[v] = inc_sum.get(v, 0.0) + float(r.median_ratio)
            inc_cnt[v] = inc_cnt.get(v, 0) + 1
    nodes["inc_ratio_sum"] = pd.Series(inc_sum)
    nodes["inc_ratio_cnt"] = pd.Series(inc_cnt)
    return src, dst, nodes, corr.set_index(CORRIDOR)["median_ratio"]


def build_features(frame, corr_art, rt_med, src, dst, nodes, corr_ratio, emb,
                   structural):
    """Assemble the design matrix. structural=False -> M2, True -> M3."""
    X = frame[["osrm_time", "osrm_distance", "dispatch_hour", "dispatch_dow"]].copy()
    for c in ["route_type", "source_state", "dest_state"]:
        X[c] = frame[c].fillna("unknown").astype("category")
    X = X.join(frame[CORRIDOR].merge(corr_art, on=CORRIDOR, how="left")
               [["corr_n", "corr_shrunk_ratio", "corr_median_actual"]]
               .set_index(frame.index))
    X = X.join(src.reindex(frame["source_center"]).set_index(frame.index))
    X = X.join(dst.reindex(frame["destination_center"]).set_index(frame.index))
    if structural:
        sn = nodes.reindex(frame["source_center"]).set_index(frame.index)
        dn = nodes.reindex(frame["destination_center"]).set_index(frame.index)
        own = corr_ratio.reindex(
            pd.MultiIndex.from_frame(frame[CORRIDOR])).to_numpy()
        for tag, nd in [("s", sn), ("d", dn)]:
            for c in ["betweenness", "clustering", "in_degree", "out_degree",
                      "throughput", "dwell_median"]:
                X[f"{tag}_{c}"] = nd[c].to_numpy()
            # exclude own corridor from the incident mean where it is present
            s_sum = nd["inc_ratio_sum"].to_numpy()
            s_cnt = nd["inc_ratio_cnt"].to_numpy()
            with np.errstate(invalid="ignore", divide="ignore"):
                excl = np.where(~np.isnan(own) & (s_cnt > 1),
                                (s_sum - own) / (s_cnt - 1), s_sum / s_cnt)
            X[f"{tag}_nbr_ratio_excl"] = excl
        se = emb.reindex(frame["source_center"]).set_index(frame.index)
        de = emb.reindex(frame["destination_center"]).set_index(frame.index)
        X = X.join(se.add_prefix("s_")).join(de.add_prefix("d_"))
    return X


def metrics(pred, actual):
    mae = float(np.mean(np.abs(pred - actual)))
    w15 = float(np.mean(np.abs(pred - actual) / actual <= 0.15))
    return mae, w15


def trip_metrics(frame, pred):
    t = pd.DataFrame({"trip": frame["trip_uuid"].to_numpy(),
                      "pred": pred, "actual": frame["actual_time"].to_numpy()})
    g = t.groupby("trip").sum()
    return metrics(g["pred"].to_numpy(), g["actual"].to_numpy())


# ------------------------------------------------ train-only artifacts (clean)
corr_art, rt_med, kappa = corridor_artifacts(train_all)
src_a, dst_a, node_a, corr_ratio = node_artifacts(train_all)
emb_train = pd.read_csv(os.path.join(CLEAN, "emb_train.csv")).set_index("center")
emb_full = pd.read_csv(os.path.join(CLEAN, "emb_full.csv")).set_index("center")
print(f"[artifacts] train-only: kappa={kappa}, corridors={len(corr_art)}, "
      f"nodes={len(node_a)}, emb dim={emb_train.shape[1]}")

# temporal sub-split for model selection: trip's FIRST od_start date decides,
# so no trip straddles fit/val (legs.csv carries od_start_time, not
# trip_creation_time - dropped at step 1)
trip_start = (pd.to_datetime(train_all["od_start_time"])
              .groupby(train_all["trip_uuid"]).transform("min"))
fit_mask = (trip_start < "2018-09-24").to_numpy()
print(f"[split] fit {fit_mask.sum()} legs (Sep 12-23) / "
      f"val {(~fit_mask).sum()} legs (Sep 24-26); test {len(test)} untouched")

y_train = train_all["actual_time"].to_numpy()
y_test = test["actual_time"].to_numpy()

GRID = [dict(learning_rate=lr, max_depth=md, max_iter=mi)
        for lr in (0.05, 0.1) for md in (None, 8) for mi in (200, 400)]


def select_and_fit(X_tr, label):
    best, best_mae = None, np.inf
    for hp in GRID:
        m = HistGradientBoostingRegressor(
            loss="absolute_error", categorical_features="from_dtype",
            random_state=SEED, **hp)
        m.fit(X_tr[fit_mask], y_train[fit_mask])
        mae = float(np.mean(np.abs(m.predict(X_tr[~fit_mask]) - y_train[~fit_mask])))
        if mae < best_mae:
            best, best_mae = hp, mae
    print(f"[{label}] selected {best} (val MAE {best_mae:.2f})")
    final = HistGradientBoostingRegressor(
        loss="absolute_error", categorical_features="from_dtype",
        random_state=SEED, **best)
    final.fit(X_tr, y_train)
    return final, best


X2_train = build_features(train_all, corr_art, rt_med, src_a, dst_a, node_a,
                          corr_ratio, emb_train, structural=False)
X2_test = build_features(test, corr_art, rt_med, src_a, dst_a, node_a,
                         corr_ratio, emb_train, structural=False)
X3_train = build_features(train_all, corr_art, rt_med, src_a, dst_a, node_a,
                          corr_ratio, emb_train, structural=True)
X3_test = build_features(test, corr_art, rt_med, src_a, dst_a, node_a,
                         corr_ratio, emb_train, structural=True)

m2, hp2 = select_and_fit(X2_train, "M2 tabular")
m3, hp3 = select_and_fit(X3_train, "M3 graph")

# ------------------------------------------------------------- predictions
osrm_np = test["osrm_time"].to_numpy()
pred = {"M0_osrm": osrm_np}
look = (test[CORRIDOR].merge(corr_art, on=CORRIDOR, how="left")
        ["corr_shrunk_ratio"].to_numpy())
fallback = test["route_type"].map(rt_med).to_numpy()
pred["M1_lookup"] = np.where(~np.isnan(look), np.nan_to_num(look) * osrm_np,
                             fallback * osrm_np)
pred["M2_tabular"] = m2.predict(X2_test)
pred["M3_graph"] = m3.predict(X3_test)

seen = test[CORRIDOR].merge(corr_art[CORRIDOR + ["corr_n"]], on=CORRIDOR,
                            how="left")["corr_n"].notna().to_numpy()
print(f"\n[test] seen-corridor legs: {seen.sum()}, cold-start legs: {(~seen).sum()}")

rows = []
for name, p in pred.items():
    mae, w15 = metrics(p, y_test)
    tmae, tw15 = trip_metrics(test, p)
    mae_s, w15_s = metrics(p[seen], y_test[seen])
    mae_u, w15_u = metrics(p[~seen], y_test[~seen])
    rows.append(dict(model=name, leg_MAE=mae, leg_w15=w15, trip_MAE=tmae,
                     trip_w15=tw15, seen_MAE=mae_s, cold_MAE=mae_u,
                     seen_w15=w15_s, cold_w15=w15_u))
    print(f"  {name:11s} leg MAE {mae:7.2f}  w15 {w15*100:5.1f}%  | trip MAE "
          f"{tmae:7.2f}  w15 {tw15*100:5.1f}%  | seen {mae_s:7.2f} / cold {mae_u:7.2f}")

# ------------------------------------------- A3 bootstrap: M2 vs M3 advantage
err2 = np.abs(pred["M2_tabular"] - y_test)
err3 = np.abs(pred["M3_graph"] - y_test)
corr_ids = pd.factorize(test["source_center"] + ">" + test["destination_center"])[0]
n_corr = corr_ids.max() + 1
sum2 = np.bincount(corr_ids, weights=err2, minlength=n_corr)
sum3 = np.bincount(corr_ids, weights=err3, minlength=n_corr)
cnt = np.bincount(corr_ids, minlength=n_corr)
cold_corr = np.unique(corr_ids[~seen])

rng = np.random.default_rng(SEED)


def boot_ci(corr_pool):
    diffs = []
    pool = np.asarray(corr_pool)
    for _ in range(B):
        idx = rng.choice(pool, len(pool), replace=True)
        c = cnt[idx].sum()
        diffs.append((sum2[idx].sum() - sum3[idx].sum()) / c)
    return np.percentile(diffs, [2.5, 97.5]), float(np.mean(diffs))


(ci_lo, ci_hi), d_mean = boot_ci(np.arange(n_corr))
(cci_lo, cci_hi), cd_mean = boot_ci(cold_corr)
overall_dem = ci_lo > 0 or ci_hi < 0
cold_dem = cci_lo > 0 or cci_hi < 0
print(f"\n[A3] graph advantage MAE(M2)-MAE(M3), corridor-cluster bootstrap "
      f"(B={B}, seed={SEED}):")
print(f"  overall:    {d_mean:+.2f} min  [{ci_lo:+.2f}, {ci_hi:+.2f}]  "
      f"-> {'DEMONSTRABLE' if overall_dem else 'NOT demonstrable'}")
print(f"  cold-start: {cd_mean:+.2f} min  [{cci_lo:+.2f}, {cci_hi:+.2f}]  "
      f"-> {'DEMONSTRABLE' if cold_dem else 'NOT demonstrable'}")

# --------------------------------------------------------- leak experiment
corr_art_f, rt_med_f, kappa_f = corridor_artifacts(legs)
src_f, dst_f, node_f, corr_ratio_f = node_artifacts(legs)
X3l_train = build_features(train_all, corr_art_f, rt_med_f, src_f, dst_f,
                           node_f, corr_ratio_f, emb_full, structural=True)
X3l_test = build_features(test, corr_art_f, rt_med_f, src_f, dst_f, node_f,
                          corr_ratio_f, emb_full, structural=True)
m3l = HistGradientBoostingRegressor(loss="absolute_error",
                                    categorical_features="from_dtype",
                                    random_state=SEED, **hp3)
m3l.fit(X3l_train, y_train)
pred_leak = m3l.predict(X3l_test)
lmae, lw15 = metrics(pred_leak, y_test)
mae3 = rows[3]["leg_MAE"]
print(f"\n[leak] M3 with FULL-data graph artifacts: leg MAE {lmae:.2f} "
      f"w15 {lw15*100:.1f}%  (clean M3: {mae3:.2f} / {rows[3]['leg_w15']*100:.1f}%)")
print(f"[leak] leakage flatters MAE by {mae3 - lmae:+.2f} min "
      f"({(mae3 - lmae) / mae3 * 100:+.1f}%)")
rows.append(dict(model="M3_LEAKY_fullgraph", leg_MAE=lmae, leg_w15=lw15,
                 trip_MAE=trip_metrics(test, pred_leak)[0],
                 trip_w15=trip_metrics(test, pred_leak)[1],
                 seen_MAE=metrics(pred_leak[seen], y_test[seen])[0],
                 cold_MAE=metrics(pred_leak[~seen], y_test[~seen])[0],
                 seen_w15=np.nan, cold_w15=np.nan))

# --------------------------------------------------------------- quantiles
qpred = {}
for q in (0.5, 0.8, 0.9):
    mq = HistGradientBoostingRegressor(loss="quantile", quantile=q,
                                       categorical_features="from_dtype",
                                       random_state=SEED, **hp3)
    mq.fit(X3_train, y_train)
    qpred[q] = mq.predict(X3_test)
    cov = float(np.mean(y_test <= qpred[q]))
    print(f"[quantile] p{int(q*100)}: empirical test coverage {cov*100:.1f}% "
          f"(target {q*100:.0f}%), median promise {np.median(qpred[q]):.0f} min")

# ------------------------------------------------------------------- save
pd.DataFrame(rows).to_csv(os.path.join(OUT, "model_comparison.csv"), index=False)
outp = test[["trip_uuid", "source_center", "destination_center", "route_type",
             "od_start_time", "osrm_time", "actual_time"]].copy()
outp["seen_corridor"] = seen
for name, p in pred.items():
    outp[name] = p
outp["M3_leaky"] = pred_leak
for q, p in qpred.items():
    outp[f"q{int(q*100)}"] = p
outp.to_csv(os.path.join(OUT, "test_predictions.csv"), index=False)
print(f"\n[saved] outputs/model_comparison.csv, outputs/test_predictions.csv "
      f"({len(outp)} test legs)")
print(f"[seeds] SEED={SEED} everywhere; hp2={hp2}; hp3={hp3}")
