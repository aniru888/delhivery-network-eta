# P4 Graph Log (step 2)

**Date:** 2026-06-11
**Script:** `scripts/02_graph.py` → `data/clean/corridor_agg.csv` (2,508 corridors), `data/clean/node_metrics.csv` (1,590 nodes). All numbers below are from this session's run output. Design references: analysis-design.md §9 A4/A5.

## Gates (all passing)

| Gate | Check | Result |
|---|---|---|
| Negative leakage self-test | a planted test-period row must trip the training-only assertion | fired — PASS |
| Training arithmetic | 18,948 legs / 10,654 trips (step-1 output / probe E3) | PASS |
| Graph ceilings | train nodes ≤ 1,657, corridors ≤ 2,783 (full-data probe C1/C2) | 1,590 / 2,508 — PASS |

## A4 — Shrinkage, executed as registered

- **κ = 6.0** (median observations per training corridor), computed once by formula before any ranking exists.
- Priors (route-type median delay ratio, training): **Carting 2.148, FTL 1.930**.
- Shrunken ratio distribution: median 2.016, p90 2.674, p99 5.582, max 21.4.
- Effect check: the worst 1-observation corridor goes raw 50.7 → shrunk 9.09. Note: 1-obs corridors can still carry high shrunk values; they are excluded from the chronic-corridor list anyway by the registered ≥5-obs support filter (design §4.1) — shrinkage orders the mid-support corridors, the filter kills the no-support ones. Both mechanisms are needed.
- 14 training corridors have both route types; majority type supplies the prior (as registered in the step-2 plan).

## A5 — Two centralities, and they disagree (finding)

Edge cost for betweenness = median actual minutes per corridor (networkx interprets weights as distances — confirmed against the stable docs this session, see design §9 A5).

| Rank | Betweenness (time-cost) | Observed throughput (trips) |
|---|---|---|
| 1 | Gurgaon_Bilaspur_HB (Haryana) | Gurgaon_Bilaspur_HB (Haryana) |
| 2 | Hyderabad_Shamshbd_H (Telangana) | Kanpur_Central_H_6 (Uttar Pradesh) |
| 3 | Pune_Tathawde_H (Maharashtra) | Bhubaneshwar_Hub (Orissa) |
| 4 | Kolkata_Dankuni_HB (West Bengal) | Bengaluru_Bomsndra_HB (Karnataka) |
| 5 | Bangalore_Nelmngla_H (Karnataka) | Surat_HUB (Gujarat) |

**Overlap: 1 of 5.** Topological centrality (where shortest paths *would* cross) and operational throughput (where shipments *actually* cross) name different hubs. Gurgaon_Bilaspur tops both — the unambiguous #1. The divergence itself goes in the report per A5: the brief's requested metric (betweenness) describes the map, not the traffic; the bottleneck ranking for the memo stays excess-minutes-based (design §4.2), with both centralities as explanation columns.

## Chain integrity (new structural finding)

Ordering each trip's legs by od_start_time: **87.2% of consecutive-leg transitions chain** (destination of leg k = source of leg k+1; 7,233 of 8,294 transitions). The remaining 12.8% "teleport" — the next leg starts somewhere other than where the previous ended (consistent with unrecorded repositioning or data gaps; cause not determinable from this file). Throughput counts only chained transitions, so it is conservative. This caps how literally "trip = path through the graph" can be taken in the report.

## Other outputs

- Node metrics: in/out-degree (corridor counts), flow in/out (leg counts), directed clustering coefficient, dwell-gap median (od-window minus driving minutes, probe D4) per source node.
- 165 nodes have no dwell proxy (never a source in training; destination-only leaves).
- Step 3 consumes `corridor_agg.csv` (chronic-corridor list: top-decile shrunk ratio among ≥5-obs corridors) and `node_metrics.csv` (hub ranking by excess minutes).
