# P4 Execution Plan

**Date:** 2026-06-11
**Inputs:** problem-statement.md, data-probe-findings.md, analysis-design.md (pre-registered 2026-06-11, before any outcome mining)
**Sequencing logic:** ordered by what the brief grades (justified graph construction, measured-not-claimed graph advantage, bottleneck audit an ops leader can act on, business translation), with a verification gate per step. Steps marked [G] produce grader-visible evidence.

## Step 1 — Clean + canonical leg table
- `scripts/01_clean.py` + `cleaning-log.md`
- Execute the open decisions from data-probe-findings.md §7: 4-part leg key (trip, source, dest, od_start); ground truth = max cumulative `actual_time` per leg (survives the 20 scan-sequence-broken legs); repair/flag those 20 with numbered log entries; drop target-derived columns (`factor`, `segment_factor`, `start_scan_to_end_scan`) at the door; backfill the 0.2% null names from the 1:1 code→name map (C4); parse state from name suffix.
- Output: one parquet/CSV leg table — corridor, route_type, dispatch hour, day-of-week, osrm_time, osrm_distance, actual_time, source/dest state, split flag.
- **Gate:** exactly 26,369 legs (verified count this session, probe §5.1); each of the 20 repaired legs has a log entry with before/after values; zero rows where actual_time ≤ 0 or osrm_time ≤ 0 (D1 says none exist — assert it).

## Step 2 — Training-period graph + corridor aggregates
- `scripts/02_graph.py`
- Directed graph from TRAINING legs only; edge attributes: leg count (flow weight), shrunken median delay ratio per design §9 A4 — (n·corridor_median + κ·route_type_median)/(n+κ), κ = median obs per training corridor, computed once and logged — and median actual minutes. Node attributes: in/out-degree, clustering coefficient, dwell proxy (D4 gap median for legs originating there), and BOTH centrality metrics per design §9 A5: (i) betweenness with edge cost = median actual minutes (networkx API verified via Context7 first — weights are costs, not volumes), (ii) observed throughput (trips passing through as intermediate stop).
- Leakage enforcement as code assertions (no test-split rows reach this script), not prose promises.
- **Gate:** train-graph node/corridor counts logged and reconciled against probe E3 arithmetic (training legs only); κ value logged before any ranking exists; a deliberate assertion test proves a test-period leg cannot enter (feed one, expect failure).

## Step 3 — Bottleneck & corridor audit [G]
- `scripts/03_bottlenecks.py` + chart outputs
- Chronic corridors per the registered definition (top-decile shrunken ratio, ≥5 obs); hub ranking by total excess minutes, with flow-weighted betweenness and dwell as explanation columns; SLA-proxy breach contribution per hub (registered §4.3).
- Visuals (brief checklist item 2): network map with bottleneck hubs and delay corridors highlighted; tornado/sensitivity of the SLA multiplier.
- **Gate:** top-5 hub list stable under corridor-cluster bootstrap (report how many of the top 5 persist across ≥80% of resamples); every memo-bound number traces to a script output file.

## Step 4 — Model contest M0–M3 + leak experiment [G]
- `scripts/04_model.py` + `model-log.md`
- M0 (OSRM as-is) → M1 (corridor lookup) → M2 (strong tabular GBM **+ node-level train aggregates** per design §9 A2) → M3 (M2 + structural-only graph features: centralities, embeddings, 1-hop neighbor delay aggregates), same learner for M2/M3, temporal validation sub-split inside training, test touched once per final model.
- [G] **Leak experiment:** M3 with full-data graph artifacts vs train-only artifacts, both test MAEs reported.
- Quantile models (p50/p80/p90) for the ETA-as-promise deliverable.
- Metrics per registered protocol: MAE + %-within-15%, leg AND trip grain (trip ground truth = sum of leg transit times per design §9 A3; end-to-end elapsed reported as separate dwell exhibit), seen/unseen corridor split, cluster-bootstrap intervals.
- "Demonstrable graph advantage" = 95% corridor-cluster-bootstrap CI of MAE(M2)−MAE(M3) excludes zero (design §9 A3) — pre-defined, not judged after the fact.
- node2vec is primary; GraphSAGE attempted only if torch-geometric installs cleanly (Context7 check on APIs before writing either). All seeds fixed and logged in model-log.md (design §9 A5).
- **Gate:** M3−M2 ablation reported with intervals against the pre-defined criterion — whichever direction it lands (honesty clause registered in analysis-design.md §3).

## Step 5 — FTL vs Carting framework [G] (amended per design §9 A1)
- `scripts/05_route_framework.py`
- **Profile-level overlap** (exact-corridor overlap = 14 training corridors / 574 legs, verified 2026-06-11 — too thin, design §9 A1): cells = distance tercile × dispatch window × intra/inter-state; a cell enters only with ≥30 training legs of EACH route type, thinner cells merge per the registered order. Within-cell comparison (observational caveat in output); counterfactual M3 scoring inside supported cells only; break-even volume per cell with cost dials. Exact-corridor comparison (14 corridors) reported as corroborating exhibit only.
- **Gate:** supported-cell table (n per route type per cell) published before any comparison; zero recommendations outside supported cells.

## Step 6 — Network Operations Strategy Memo (1–2 pages) [G]
- Answer-first: top-5 hubs with excess-minutes and SLA-breach contribution on the first half-page; corridor-specific interventions (parallel route / facility upgrade / route-type shift) each tied to a measured number; top-3-hub upgrade quantification with the stated proxy assumptions and sensitivity; ETA-promise dial (p80 vs p90 trade-off) as the standing decision.
- Measured numbers lead (minutes, breach %, corridor names); rupee figures appear only as bounded ranges with their three dials exposed (SLA proxy × shipment value × penalty fraction), PLUS a **recoverable-fraction dial** on excess minutes — actual−OSRM is partly definitional (OSRM excludes handling), so a hub upgrade cannot recover all of it; presenting gross excess minutes as the prize would inflate the recommendation by construction.
- "Steady-state, non-peak" scope statement (22 days, pre-festival, registered §7).
- md → PDF via repo `scripts/md2pdf.py` (P2 toolchain).
- **Gate:** ≤2 pages; written for an ops leader (no model jargon in body); every number traces to a step-3/4/5 output.

## Step 7 — Technical documentation + visuals package
- README for the pipeline (brief checklist item 1), reproducible run order, assumptions register, model-comparison table (checklist item 3).
- **Gate:** cold re-run of scripts 01→05 reproduces every reported number (verification-before-completion) — requires the fixed seeds from design §9 A5; a re-run that drifts means a seed leaked.

## Step 8 — Adversarial self-review
- case-judge Judge mode against the brief's five deliverables; hardball Q&A ("why is your chronic threshold different from ours?", "is the graph advantage worth the pipeline complexity?", "where do the revenue numbers come from?"); fix what fails.

## Open items needing user input
1. **Deadline / submission format:** brief lists POCs (Saksham Gupta, Yashvi Mehta) but no date — same ambiguity as P2/P3.
2. **Streamlit dashboard:** optional in the brief (checklist item 6). P3's Streamlit prototype precedent exists; default = build only after Steps 1–6 are done, veto welcome.
3. **GraphSAGE attempt:** contingent on torch-geometric installing cleanly on this Windows machine; node2vec is the registered primary either way.
