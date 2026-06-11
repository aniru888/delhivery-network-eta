"""P4 step 3: bottleneck & corridor audit.

Executes execution-plan.md step 3 under the registered definitions
(analysis-design.md section 4, amended section 9):
  - Chronic corridor: top decile of SHRUNK ratio among >=5-obs training
    corridors (registered 4.1); ranked by SLA-breach contribution (brief task 2).
  - Bottleneck hub: ranked by total excess minutes on incident corridors
    (registered 4.2b); betweenness/throughput/dwell as explanation columns.
  - SLA proxy (registered 4.3): promised = OSRM x network median ratio
    (training-calibrated); breach = actual > promised x 1.2; sensitivity over
    the breach margin reported, because both constants are constructed.
  - Stability gate: corridor-cluster bootstrap (B=1000, seed=42 per A5);
    each observed top-5 hub must appear in >=80% of resampled top-5 lists.

TRAINING legs only (same leakage rule as step 2).

Run:  python scripts/03_bottlenecks.py   (from the project folder)
Outputs: outputs/ (chronic_corridors.csv, hub_ranking.csv, 3 charts) + stdout.
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
CLEAN = os.path.join(PROJ, "data", "clean")
OUT = os.path.join(PROJ, "outputs")
os.makedirs(OUT, exist_ok=True)

SEED = 42
B = 1000
CORRIDOR = ["source_center", "destination_center"]

legs = pd.read_csv(os.path.join(CLEAN, "legs.csv"))
agg = pd.read_csv(os.path.join(CLEAN, "corridor_agg.csv"))
nodes = pd.read_csv(os.path.join(CLEAN, "node_metrics.csv")).set_index("center")

train = legs[legs["data"] == "training"].copy()
assert len(train) == 18948, "LEAKAGE GATE: training leg count drifted"
train["excess_min"] = train["actual_time"] - train["osrm_time"]

name_map = (pd.concat([
    train.rename(columns={"source_center": "c", "source_name": "n"})[["c", "n"]],
    train.rename(columns={"destination_center": "c", "destination_name": "n"})[["c", "n"]]])
    .dropna().drop_duplicates("c").set_index("c")["n"])


def short(code):
    return str(name_map.get(code, code)).split(" (")[0]


# ------------------------------------------------- SLA proxy (registered 4.3)
med_ratio = (train["actual_time"] / train["osrm_time"]).median()
train["promised_min"] = train["osrm_time"] * med_ratio
train["breach"] = train["actual_time"] > train["promised_min"] * 1.2
print(f"[SLA] promise calibration: network median ratio = {med_ratio:.3f} "
      f"(promised = OSRM x {med_ratio:.3f}); breach margin 1.2")
print(f"[SLA] training breach rate under proxy: {train['breach'].mean()*100:.1f}% of legs")

margins = [1.0, 1.1, 1.2, 1.3, 1.5]
sens = {m: (train["actual_time"] > train["promised_min"] * m).mean() for m in margins}
print("[SLA] sensitivity, breach rate by margin: "
      + ", ".join(f"x{m}={v*100:.1f}%" for m, v in sens.items()))

# ------------------------------- chronic corridors (registered 4.1, amended A4)
eligible = agg[agg["n_legs"] >= 5].copy()
cut = eligible["shrunk_ratio"].quantile(0.9)
chronic = eligible[eligible["shrunk_ratio"] >= cut].copy()
print(f"\n[chronic] eligible corridors (>=5 train obs): {len(eligible)} "
      f"of {len(agg)}; top-decile shrunk-ratio cut = {cut:.3f}; "
      f"chronic corridors = {len(chronic)}")

corr_stats = (train.groupby(CORRIDOR)
              .agg(excess_min_total=("excess_min", "sum"),
                   breached_legs=("breach", "sum"),
                   legs_total=("breach", "size")).reset_index())
chronic = chronic.merge(corr_stats, on=CORRIDOR, how="left", validate="1:1")
chronic = chronic.sort_values("breached_legs", ascending=False)
chronic["source_short"] = chronic["source_center"].map(short)
chronic["dest_short"] = chronic["destination_center"].map(short)
chronic.to_csv(os.path.join(OUT, "chronic_corridors.csv"), index=False)

# composition of the chronic list vs the eligible pool (pattern check)
state = legs.drop_duplicates("source_center").set_index("source_center")["source_state"]
state = pd.concat([state, legs.drop_duplicates("destination_center")
                   .set_index("destination_center")["dest_state"]]).groupby(level=0).first()
for label, frame in [("eligible", eligible.merge(corr_stats, on=CORRIDOR, how="left")),
                     ("chronic", chronic)]:
    intra = (frame["source_center"].map(state) == frame["destination_center"].map(state)).mean()
    carting = (frame["major_route_type"] == "Carting").mean()
    print(f"[chronic] {label}: intra-state {intra*100:.0f}%, Carting {carting*100:.0f}% "
          f"(n={len(frame)})")
chronic_breach_rate = chronic["breached_legs"] / chronic["legs_total"]
print(f"[chronic] per-corridor breach rate on the chronic list: "
      f"median {chronic_breach_rate.median()*100:.0f}%, "
      f"min {chronic_breach_rate.min()*100:.0f}%, max {chronic_breach_rate.max()*100:.0f}%")
print("[chronic] top 10 by SLA-breach contribution (brief task-2 ranking):")
print(chronic[["source_short", "dest_short", "major_route_type", "n_legs",
               "median_ratio", "shrunk_ratio", "breached_legs",
               "excess_min_total"]].head(10).to_string(index=False))

# ----------------------------------- hub ranking by excess minutes (4.2b)
corr_excess = corr_stats.set_index(CORRIDOR[0]), corr_stats.set_index(CORRIDOR[1])
hub_excess = (corr_stats.groupby("source_center")["excess_min_total"].sum()
              .add(corr_stats.groupby("destination_center")["excess_min_total"].sum(),
                   fill_value=0))
hub_breach = (corr_stats.groupby("source_center")["breached_legs"].sum()
              .add(corr_stats.groupby("destination_center")["breached_legs"].sum(),
                   fill_value=0))
hub = pd.DataFrame({"excess_min_total": hub_excess, "breached_legs": hub_breach})
hub = hub.join(nodes[["betweenness_time_cost", "throughput_trips",
                      "dwell_gap_median_min", "flow_in_legs", "flow_out_legs"]])
hub["name"] = [short(c) for c in hub.index]
hub = hub.sort_values("excess_min_total", ascending=False)
# NOTE (logged): a leg's excess counts toward BOTH endpoints - attribution
# overlaps across hubs; valid for ranking, not additive across the top-5.
network_total = train["excess_min"].sum()
top5 = hub.head(5)
top5_share = top5["excess_min_total"].sum() / (2 * network_total)
print(f"\n[hubs] network total excess: {network_total/60:,.0f} hours over 15 train days")
print(f"[hubs] top-5 hubs touch {top5_share*100:.1f}% of all endpoint-attributed excess")
print(hub.head(10)[["name", "excess_min_total", "breached_legs",
                    "betweenness_time_cost", "throughput_trips",
                    "dwell_gap_median_min"]].to_string())
hub.reset_index().to_csv(os.path.join(OUT, "hub_ranking.csv"), index=False)

# --------------------------------------- bootstrap stability gate (plan step 3)
rng = np.random.default_rng(SEED)
observed_top5 = list(top5.index)
hits = {h: 0 for h in observed_top5}
src_arr = corr_stats["source_center"].to_numpy()
dst_arr = corr_stats["destination_center"].to_numpy()
exc_arr = corr_stats["excess_min_total"].to_numpy()
n_corr = len(corr_stats)
for _ in range(B):
    idx = rng.integers(0, n_corr, n_corr)
    s = pd.Series(exc_arr[idx], index=src_arr[idx]).groupby(level=0).sum()
    d = pd.Series(exc_arr[idx], index=dst_arr[idx]).groupby(level=0).sum()
    bs_top5 = set(s.add(d, fill_value=0).nlargest(5).index)
    for h in observed_top5:
        if h in bs_top5:
            hits[h] += 1
print(f"\n[stability] corridor-cluster bootstrap (B={B}, seed={SEED}):")
worst = 1.0
for h in observed_top5:
    p = hits[h] / B
    worst = min(worst, p)
    print(f"  {short(h):28s} in resampled top-5: {p*100:.1f}%")
gate_pass = worst >= 0.8
print(f"[gate] every top-5 hub persists in >=80% of resamples: "
      f"{'PASS' if gate_pass else 'FAIL'} (worst {worst*100:.1f}%)")
if not gate_pass:
    print("[gate] FAIL is a reportable result: the ranking tail is unstable; "
          "memo names only the stable subset.")

# ------------------------------------------------------------------ charts
# 1. network map - insight title computed from data
G = nx.DiGraph()
for r in corr_stats.itertuples(index=False):
    G.add_edge(r.source_center, r.destination_center)
pos = nx.spring_layout(G, seed=SEED, k=0.08)
fig, ax = plt.subplots(figsize=(14, 11))
sizes = nodes["throughput_trips"].reindex(list(G.nodes())).fillna(0)
sizes = 6 + 240 * (sizes / max(sizes.max(), 1))
nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.05, arrows=False, width=0.4)
chronic_edges = list(zip(chronic["source_center"], chronic["destination_center"]))
nx.draw_networkx_edges(G, pos, edgelist=chronic_edges, ax=ax, alpha=0.7,
                       arrows=False, width=1.4, edge_color="#c0392b")
nx.draw_networkx_nodes(G, pos, ax=ax, node_size=sizes, node_color="#b8c4cc",
                       linewidths=0)
nx.draw_networkx_nodes(G, pos, nodelist=observed_top5, ax=ax,
                       node_size=sizes.reindex(observed_top5).fillna(60) + 140,
                       node_color="#1a4a72", linewidths=0)
for i, h in enumerate(observed_top5, 1):
    ax.annotate(str(i), pos[h], fontsize=11, fontweight="bold", color="white",
                ha="center", va="center")
legend_txt = "\n".join(f"{i}. {short(h)}" for i, h in enumerate(observed_top5, 1))
ax.text(0.01, 0.01, "Top-5 hubs by excess minutes\n" + legend_txt,
        transform=ax.transAxes, fontsize=10, va="bottom",
        bbox=dict(facecolor="white", edgecolor="#888", alpha=0.9))
ax.set_title(f"5 hubs touch {top5_share*100:.0f}% of network excess delay; "
             f"{len(chronic)} chronic corridors (red) concentrate the worst ratios",
             fontsize=13)
ax.axis("off")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "bottleneck_map.png"), dpi=160)
plt.close(fig)

# 2. SLA sensitivity
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(margins, [sens[m] * 100 for m in margins], marker="o", color="#1a4a72")
for m in margins:
    ax.annotate(f"{sens[m]*100:.0f}%", (m, sens[m] * 100), xytext=(0, 8),
                textcoords="offset points", ha="center", fontsize=9)
ax.set_xlabel("breach margin (x promised time)")
ax.set_ylabel("% of legs breaching")
ax.set_title(f"Breach rate falls {sens[1.0]*100:.0f}% -> {sens[1.5]*100:.0f}% as the margin "
             "moves 1.0x -> 1.5x:\nthe SLA constant is a policy dial, not a fact",
             fontsize=11)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "sla_sensitivity.png"), dpi=160)
plt.close(fig)

# 3. top chronic corridors by breach contribution
top_c = chronic.head(12).iloc[::-1]
lab = top_c["source_short"] + " > " + top_c["dest_short"]
fig, ax = plt.subplots(figsize=(10, 6))
ax.barh(lab, top_c["breached_legs"], color="#c0392b", alpha=0.85)
for i, (b, n) in enumerate(zip(top_c["breached_legs"], top_c["n_legs"])):
    ax.annotate(f"{int(b)} of {int(n)}", (b, i), xytext=(4, -3),
                textcoords="offset points", fontsize=8)
rate12 = (chronic.head(12)["breached_legs"] / chronic.head(12)["legs_total"])
ax.set_xlabel("SLA-breaching legs (training, proxy SLA)")
ax.set_title(f"The 12 worst corridors breach on {rate12.min()*100:.0f}-"
             f"{rate12.max()*100:.0f}% of their runs - chronic, not random",
             fontsize=12)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "chronic_corridors.png"), dpi=160)
plt.close(fig)

print(f"\n[saved] outputs/: chronic_corridors.csv ({len(chronic)}), hub_ranking.csv "
      f"({len(hub)}), bottleneck_map.png, sla_sensitivity.png, chronic_corridors.png")
