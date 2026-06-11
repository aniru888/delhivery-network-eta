"""P4 step 2: training-period graph + corridor aggregates.

Executes execution-plan.md step 2 under analysis-design.md section 9 amendments:
  A4 - shrunken corridor ratio = (n*corridor_median + kappa*prior)/(n + kappa),
       kappa = median observations per TRAINING corridor, computed once, logged.
  A5 - two centrality metrics: (i) betweenness with edge cost = median actual
       minutes (networkx docs, verified this session: "weights are interpreted
       as distances"), (ii) observed throughput = trips passing through the
       node as an intermediate stop (dest of leg k == source of leg k+1).

Leakage rule: this script sees TRAINING legs only. Enforced by assertion in
build_inputs(); a negative self-test feeds a test-period row and requires the
assertion to fire (execution-plan step 2 gate).

Run:  python scripts/02_graph.py   (from the project folder)
Outputs: data/clean/corridor_agg.csv, data/clean/node_metrics.csv
"""

import os

import networkx as nx
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
CLEAN = os.path.join(PROJ, "data", "clean")

CORRIDOR = ["source_center", "destination_center"]


def build_inputs(frame):
    """Gate: only training-split legs may enter graph construction."""
    assert (frame["data"] == "training").all(), \
        "LEAKAGE: non-training rows reached graph construction"
    return frame


legs = pd.read_csv(os.path.join(CLEAN, "legs.csv"))

# ---- negative self-test: a test-period leg MUST trip the leakage assertion
_test_probe = legs[legs["data"] == "test"].head(1)
try:
    build_inputs(pd.concat([legs[legs["data"] == "training"].head(2), _test_probe]))
    raise SystemExit("GATE FAILED: leakage assertion did NOT fire on a test row")
except AssertionError:
    print("[gate] negative leakage self-test: assertion fired on a planted test row - PASS")

train = build_inputs(legs[legs["data"] == "training"].copy())

# ---- gates: reconcile against step-1 / probe-E3 arithmetic
assert len(train) == 18948, f"GATE FAILED: {len(train)} training legs, expected 18948"
assert train["trip_uuid"].nunique() == 10654, \
    f"GATE FAILED: {train['trip_uuid'].nunique()} training trips, expected 10654"
print(f"[gate] training legs 18,948 / trips 10,654 - PASS")

train["ratio"] = train["actual_time"] / train["osrm_time"]

# ------------------------------------------------------- corridor aggregates
grp = train.groupby(CORRIDOR)
agg = grp.agg(n_legs=("ratio", "size"),
              median_ratio=("ratio", "median"),
              median_actual_min=("actual_time", "median"),
              median_osrm_min=("osrm_time", "median"),
              median_osrm_km=("osrm_distance", "median")).reset_index()

# majority route type per corridor (prior target for shrinkage)
rt_counts = (train.groupby(CORRIDOR + ["route_type"]).size()
             .rename("n").reset_index()
             .sort_values(["source_center", "destination_center", "n"],
                          ascending=[True, True, False]))
rt_major = rt_counts.drop_duplicates(CORRIDOR)[CORRIDOR + ["route_type"]]
rt_major = rt_major.rename(columns={"route_type": "major_route_type"})
agg = agg.merge(rt_major, on=CORRIDOR, how="left", validate="1:1")
mixed = (train.groupby(CORRIDOR)["route_type"].nunique() > 1).sum()
print(f"[info] corridors with both route types in training: {mixed} "
      f"(majority type used as shrinkage prior)")

# A4: kappa fixed by formula BEFORE any ranking exists
kappa = float(agg["n_legs"].median())
rt_median = train.groupby("route_type")["ratio"].median()
print(f"[A4] kappa = median obs per training corridor = {kappa}")
print(f"[A4] shrinkage priors (route-type median ratio): "
      + ", ".join(f"{k}={v:.3f}" for k, v in rt_median.items()))

prior = agg["major_route_type"].map(rt_median)
agg["shrunk_ratio"] = ((agg["n_legs"] * agg["median_ratio"] + kappa * prior)
                       / (agg["n_legs"] + kappa))

# ------------------------------------------------------------------- graph
G = nx.DiGraph()
for row in agg.itertuples(index=False):
    G.add_edge(row.source_center, row.destination_center,
               n_legs=int(row.n_legs),
               shrunk_ratio=float(row.shrunk_ratio),
               median_actual_min=float(row.median_actual_min))
print(f"[graph] training graph: {G.number_of_nodes()} nodes, "
      f"{G.number_of_edges()} corridors (probe ceilings: 1,657 / 2,783)")
assert G.number_of_nodes() <= 1657 and G.number_of_edges() <= 2783, \
    "GATE FAILED: training graph exceeds full-data probe counts"

# --------------------------------------------------------------- node metrics
# A5 metric (i): brief's betweenness, edge cost = median actual minutes
btw = nx.betweenness_centrality(G, weight="median_actual_min", normalized=True)
# directed clustering coefficient (brief task 2)
clust = nx.clustering(G)

# A5 metric (ii): observed throughput - trips crossing the node as an
# intermediate stop. Legs ordered by od_start_time within trip; node counts
# when it is destination of leg k AND source of leg k+1.
seq = train.sort_values(["trip_uuid", "od_start_time"])
throughput = {}
chained = 0
pairs = 0
for _, g in seq.groupby("trip_uuid", sort=False):
    dsts = g["destination_center"].tolist()
    srcs = g["source_center"].tolist()
    for k in range(len(g) - 1):
        pairs += 1
        if dsts[k] == srcs[k + 1]:
            chained += 1
            throughput[dsts[k]] = throughput.get(dsts[k], 0) + 1
print(f"[A5] consecutive-leg chain integrity: {chained}/{pairs} "
      f"({chained / max(pairs, 1) * 100:.1f}%) of transitions chain "
      f"dest(k)==src(k+1); only chained transitions count toward throughput")

# dwell proxy: od-window minutes minus driving minutes, legs originating there
train["dwell_gap"] = train["od_duration_min"] - train["actual_time"]
dwell = train.groupby("source_center")["dwell_gap"].median()

flow_out = train.groupby("source_center").size()
flow_in = train.groupby("destination_center").size()

nodes = pd.DataFrame({"center": list(G.nodes())}).set_index("center")
nodes["out_degree"] = pd.Series(dict(G.out_degree()))
nodes["in_degree"] = pd.Series(dict(G.in_degree()))
nodes["flow_out_legs"] = flow_out.reindex(nodes.index).fillna(0).astype(int)
nodes["flow_in_legs"] = flow_in.reindex(nodes.index).fillna(0).astype(int)
nodes["betweenness_time_cost"] = pd.Series(btw)
nodes["clustering_directed"] = pd.Series(clust)
nodes["throughput_trips"] = pd.Series(throughput).reindex(nodes.index).fillna(0).astype(int)
nodes["dwell_gap_median_min"] = dwell.reindex(nodes.index)
n_no_dwell = nodes["dwell_gap_median_min"].isna().sum()
print(f"[info] nodes with no dwell proxy (never a source in training): {n_no_dwell}")

# ------------------------------------------------------------------- save
agg.to_csv(os.path.join(CLEAN, "corridor_agg.csv"), index=False)
nodes.reset_index().to_csv(os.path.join(CLEAN, "node_metrics.csv"), index=False)
print(f"[saved] corridor_agg.csv ({len(agg)} corridors), "
      f"node_metrics.csv ({len(nodes)} nodes)")

print("\n[summary] shrunk_ratio: "
      + agg["shrunk_ratio"].describe(percentiles=[.5, .9, .99]).round(3)
      .to_string().replace("\n", " | "))
print("[summary] raw median_ratio for 1-obs corridors before/after shrinkage: "
      f"max raw {agg.loc[agg.n_legs == 1, 'median_ratio'].max():.2f} -> "
      f"max shrunk {agg.loc[agg.n_legs == 1, 'shrunk_ratio'].max():.2f}")
top_btw = nodes["betweenness_time_cost"].nlargest(5)
top_thr = nodes["throughput_trips"].nlargest(5)
print("[summary] top-5 betweenness (time-cost):", list(top_btw.index))
print("[summary] top-5 observed throughput:   ", list(top_thr.index))
overlap = len(set(top_btw.index) & set(top_thr.index))
print(f"[summary] overlap between the two top-5 lists: {overlap}/5 "
      "(divergence = topological vs operational importance, reported per A5)")
