# P4 Data Probe Findings (pre-plan audit)

**Date:** 2026-06-11
**Source:** `scripts/00_probe.py` run this session; full output in `probe-report.txt`. Every number below traces to a probe section (cited as A–F).
**Discipline note:** this audit covers structure, quality, and anomalies only. No delay-vs-feature relationships were mined; the analysis design gets pre-registered after this audit (P3 precedent).

## 1. What the brief asks (problem-statement.md)

Five deliverables, graded as a consulting package, not a model dump:

1. **Graph construction** — directed weighted graph, edge weights = median actual-vs-OSRM delay ratio per corridor, stratified by route type and time of day. Choices justified, not just applied.
2. **Bottleneck audit** — betweenness centrality, in/out-degree, clustering coefficients; "chronically delayed" defined in the brief as actual > OSRM by >20%; rank by SLA breach contribution.
3. **ETA model** — baseline regression vs GraphSAGE/node2vec-enhanced model; the graph advantage "must be measured, not claimed" (MAE + % of trips within 15% of actual).
4. **FTL vs Carting framework** — ML-backed route-type selection accounting for the source facility's graph position.
5. **1–2 page Network Operations Strategy Memo** — top 5 bottleneck hubs with SLA breach contribution, corridor interventions, revenue-at-risk recovered if top 3 hubs upgraded.

Optional: Streamlit dashboard. Contacts: Saksham Gupta, Yashvi Mehta. No deadline stated in the brief (same ambiguity as P2/P3).

## 2. Verified data structure

One file: `delivery_data.csv`, 144,867 × 24, zero exact-duplicate rows; only nulls are `source_name` 293 / `destination_name` 261 (~0.2%) — center *codes* are never null (A).

**The headline structural fact (B1/B3/B4): three-level hierarchy, cumulative counters per leg.**

| Level | Count | Meaning |
|---|---|---|
| Trip (`trip_uuid`) | 14,817 | one vehicle journey; route_type, schedule, creation time constant within trip (B2) |
| OD leg (trip, source, dest) | 26,368 | one corridor traversal; od_start/end constant within leg (B2) |
| Scan row | 144,867 | intermediate scan points, ~5.5 per leg (B1) |

- Within a leg, `actual_time` / `osrm_time` / `osrm_distance` are **cumulative**: first row's cumulative equals its segment value in 26,368 of 26,368 legs (B4, decisive), non-decreasing in file order in 99.92% of legs (B3).
- `segment_*` fields are **per-row increments**: their leg-sum reproduces the last cumulative within ±2 min in 84.4% of legs, median gap 1 min (B3). The drift is rounding accumulation — **the leg's last cumulative row is ground truth; never sum segments** (OSRM cumulative-vs-segment-sum agrees within ±2 in only ~64% of legs, B3).
- The counter **resets at every leg**, it does not run across the trip: B4's 100% first-row equality is the decisive test. (B5's 1,947 "carry-looking" transitions are just next legs whose first segment is longer than the previous leg's total.)
- 1 trip = 1–8 legs; 60% of trips are single-leg (B1).
- `factor` ≡ `actual_time/osrm_time` row-wise to <0.01 in 100% of rows (D2) — derived, carries no independent information. Same for `segment_factor` (98.4%, remainder are zero-OSRM denominators).
- `start_scan_to_end_scan` ≡ od_end − od_start rounded down (diff ∈ [−1, 0] min in all 144,867 rows, D3) — fully redundant with the timestamps.

**Unit of analysis going forward: the LEG** (last cumulative row per leg = one corridor traversal observation). Corridor = directed (source_center, destination_center) pair aggregating legs.

## 3. Graph yield (Rule-11 units: usable corridors, not "file loads")

- **1,657 nodes** (1,508 source ∪ 1,481 destination centers), **2,783 directed corridors** (C1/C2).
- Observations per corridor: median 7; ≥5 obs in 58.6% of corridors covering **91.7% of legs**; ≥20 obs in only 9.6% (C2).
- Stratified by route type the density roughly halves: Carting 1,071 corridors (60.4% with ≥5 obs), FTL 1,735 (56.8%) (C3).
- **Rule-11 verdict:** corridor-level median delay ratio is feasible for the network that matters. The brief's full stratification (corridor × route type × time-of-day) is NOT supported for most cells — adding time-of-day on top of route type pushes most cells below 5 obs. Design must use hierarchical fallback (corridor → corridor×type with shrinkage toward corridor/network medians), documented as a justified deviation.
- Hub skew: top-20 centers account for 25.6% of leg endpoints; the heaviest (`IND000000ACB` = Gurgaon_Bilaspur_HB (Haryana), 1,991 legs; name verified against the data this session) is ~1.4× the next, Bangalore_Nelmngla_H (F6). Good news for the bottleneck audit: structure is concentrated.
- Code↔name mapping is 1:1 wherever the name exists (C4); state is parseable from the `(State)` suffix in 100% of non-null names (C5). Top states: Haryana, Maharashtra, Karnataka.

## 4. Target integrity — and the finding that breaks the brief's threshold

- Leg-level delay ratio (actual/OSRM): median **2.00**, p5 1.195, p95 5.249 (D1).
- **98.3% of legs run slower than OSRM; 94.8% exceed the brief's ">20% = chronically delayed" threshold** (D1). The brief's premise ("underestimates on a significant fraction of routes") is empirically "underestimates on essentially all routes," because OSRM models drive time while actual time includes dwell/handling. Consequence: the >20% rule flags 95% of the network and ranks nothing. "Chronic delay" must be defined **relative to the network distribution** (e.g., corridor median ratio in the top decile, or above network median by a margin) — a justified, documented deviation from the brief, backed by D1.
- No zero/negative/null `actual_time` or `osrm_time` at leg level (D1).
- od-window duration exceeds the leg's cumulative driving time by median ~50 min, p99 ~646 min (D4) — the od window contains dwell that `actual_time` itself may not fully capture. Semantics of `actual_time` (pure transit vs transit+some dwell) are not documented anywhere in the data [inferred from D4; exact composition unknown].

## 5. Anomaly inventory (all verified)

1. **21 non-monotonic legs (B3) = 21 negative `segment_actual_time` rows (F1):** only ONE is a true OD-pair revisit separable by od_start_time (F4; corrected key (trip, source, dest, od_start) yields 26,369 legs vs 26,368 — verified this session). The other 20 are non-monotonic *within* a single od window — scan-sequence errors (F5 sample: cumulative 38→12→48). **Fix: adopt the 4-part leg key AND repair/flag the 20 broken legs at cleaning time** (last cumulative row is still usable if the max, not last, is taken — decision logged in cleaning).
2. **`cutoff_factor` semantics unknown:** NOT the cumulative time at cutoff (|cutoff_factor − actual_time| < 1 in only 0.18% of rows, F2); scale resembles minutes (median 66, max 1,927, B7). `is_cutoff` is True on 82% of rows (B7). No data dictionary explains these. Decision: treat as opaque — exclude from features unless semantics get established; document.
3. **`actual_distance_to_destination` is misnamed:** monotonic *increasing* within 95.8% of legs (B6), last value ≈ 0.80 × osrm_distance (median, F3) → it is cumulative distance *traveled*, on a metric that runs ~20% short of OSRM road distance [inferred: geodesic vs road, unverified]. Do not use as "remaining distance."
4. **Segment-level zeros:** segment_actual_time 1,952 zeros + segment_osrm_time 2,347 zeros → 1,717 NaN `segment_factor` rows (D5/D2). Harmless if we aggregate at leg level from cumulative fields.
5. **Name nulls (0.2%, A):** codes complete, but backfill from other rows of the same code yields ZERO (verified in 01_clean.py E2: null-name codes are unnamed everywhere in the file). 66 source + 81 dest legs carry null state; handled as an explicit "unknown" category, not imputed.

Clean elsewhere: no exact-dup rows (A), no trips spanning splits (E3), no od_end < od_start (D3), route_type/schedule/creation constant within trip (B2), full 24h × 22-day coverage with no unparseable timestamps (E1).

## 6. Leakage traps (the brief grades "measured, not claimed")

1. **The split is temporal and must gate the graph.** `data` column: training = Sep 12–26 (10,654 trips), test = Sep 27–Oct 3 (4,163 trips), zero trip overlap (E3). Every graph artifact — corridor medians, centrality, node2vec/GraphSAGE embeddings — must be computed on **training-period legs only**. Embeddings learned on the full graph encode test-period delays into node features: this is the project's equivalent of P3's CLV leak.
2. **Leak-measurement experiment (P3 precedent, carries the grading):** train one graph model with full-data graph features, one with train-only features; report both MAEs. "Graph leakage inflates accuracy from X to Y" turns the brief's top criterion into a measured result.
3. **Cold start is real: 15.2% of test corridors (275 of 1,805) never appear in training** (E3). The model needs an explicit fallback path, and results must be reported split by seen/unseen corridor — this is also where graph embeddings should genuinely help (neighbors exist even when the corridor is new).
4. **Target-derived columns:** `factor`, `segment_factor` (≡ target ratio, D2), `start_scan_to_end_scan` / od timestamps (≡ realized duration, D3/D4) are outcome encodings — forbidden as features.
5. **22 days of data (Sep 12–Oct 3, 2018, E1):** "seasonal volume spikes" from the brief are unobservable. Time-of-day and day-of-week are the only defensible temporal features; say so plainly rather than hand-waving seasonality.

## 7. Open decisions (for the design phase, not decided here)

1. Prediction unit: leg-level ETA (then compose trips) vs trip-level directly. Leg-level is the natural grain (26,368 obs, corridor features attach cleanly); trip-level is what an ops leader quotes. Likely: model legs, evaluate both grains.
2. Chronic-delay definition replacing the >20% rule (see §4) — pre-register the definition before ranking corridors.
3. Sparse-corridor handling: shrinkage/hierarchical pooling for the 41.4% of corridors with <5 obs (C2).
4. cutoff fields in or out (§5.2).
5. GraphSAGE vs node2vec (brief allows either): library choice and API to be verified via Context7 at build time, not from memory.
6. Streamlit dashboard (optional in brief) — user call, same as P3's prototype decision.
7. SLA definition for "breach contribution": no SLA column exists; needs a constructed proxy (e.g., promised = OSRM-based ETA + buffer). Must be explicit in the memo.

## 8. Modeling-population arithmetic (E3)

- 14,817 trips → 10,654 training (Sep 12–26) + 4,163 test (Sep 27–Oct 3), no overlap
- 26,368 legs over 2,783 directed corridors on 1,657 nodes
- Trip mix: 8,908 Carting + 5,909 FTL (E2)
- Test exposure: 1,805 test corridors, of which 275 (15.2%) unseen in training
