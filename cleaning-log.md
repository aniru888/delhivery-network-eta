# P4 Cleaning Log (step 1)

**Date:** 2026-06-11
**Script:** `scripts/01_clean.py` → `data/clean/legs.csv` (26,369 legs × 17 cols). Every entry below is from the script's run output this session; gates are hard assertions in the script, all passing.

## E1 — Target-derived and opaque columns dropped at the door

`factor`, `segment_factor` (≡ actual/OSRM ratio row-wise, probe D2), `start_scan_to_end_scan` (≡ realized od duration, probe D3) — outcome encodings, banned as features per analysis-design.md §2. Also dropped: `is_cutoff`, `cutoff_factor`, `cutoff_timestamp` — semantics unestablished (probe F2: cutoff_factor matches cumulative time in 0.18% of rows; no data dictionary). Registered decision data-probe-findings.md §7.4: opaque fields stay out.

## E2 — Name backfill attempted, yield ZERO (finding, not silent skip)

293 source-name + 261 destination-name null scan rows. The planned remedy (code→name map from other rows of the same code) recovered **none**: every null-name code is unnamed everywhere in the file. Consequence: 66 source-state + 81 dest-state nulls at leg level (0.25%/0.31% of 26,369). Handling: explicit "unknown" state category downstream, no imputation. The findings doc §5.5 was corrected to match this empirical result.

## E3 — Scan rows → legs; 20 broken legs repaired by max()

- Leg key: (trip_uuid, source_center, destination_center, od_start_time) — splits the one true OD-revisit (probe F4) from the rest; 26,368 → 26,369 legs.
- Cumulative fields (`actual_time`, `osrm_time`, `osrm_distance`) aggregated by **max**, not last: identical on the 99.92% monotonic legs, and repairs the 20 scan-sequence-broken legs (probe B3/F5). All 20 are listed with full cumulative sequences in the script output; the breaks are single dips in otherwise increasing sequences (e.g. `..., 1097, 1040, 1148, ...`), so max = the leg's true final cumulative in every case inspected.
- `n_scan_rows` retained per leg; sum reconciles to 144,867 (gate G2).

## E4 — Dispatch context + one outcome-side audit column

- `dispatch_hour`, `dispatch_dow` from `od_start_time` (known pre-dispatch; trip_creation_time is trip-level and adds nothing at leg grain).
- `od_duration_min` (od_end − od_start) carried **for the step-3 dwell audit only** (probe D4) — outcome-side, flagged in the script comment, never a model feature.

## E5 — State parsed from verified "(State)" name suffix

100% parse rate on named legs (probe C5); nulls equal the E2 residual exactly (66/81).

## Gates (all hard assertions, all passing this session)

| Gate | Check | Result |
|---|---|---|
| G1 | leg count == 26,369 (pre-verified count, findings §5.1) | pass |
| G2 | Σ n_scan_rows == 144,867 | pass |
| G3 | actual_time > 0 and osrm_time > 0 on every leg | pass |
| G4 | no trip_uuid straddles train/test | pass |
| G5 | leg key unique | pass |
| G6 | route_type ∈ {FTL, Carting}, dispatch context parsed on every leg | pass |

## Output reconciliation

- Split: 18,948 training / 7,421 test legs (trips: 10,654 / 4,163, probe E3).
- Route type at leg level: 13,940 FTL / 12,429 Carting — FTL is +1 vs probe C3's 3-part-key count because the split OD-revisit leg (F4) is FTL.
