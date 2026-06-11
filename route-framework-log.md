# P4 Route Framework Log (step 5)

**Date:** 2026-06-11
**Script:** `scripts/05_route_framework.py` → `outputs/route_framework.csv` (10 cells), `outputs/route_framework.png`. Executed per amendment A1 (analysis-design.md §9); seed 42, M3 re-fit with step-4 hypers. All numbers from this session's run.

## Gate (published before any comparison, as registered)

Profile cells = distance tercile (33.6 / 68.6 km training splits) × dispatch window (day 06–18 / night) × intra/inter-state. Support = ≥30 training legs of EACH route type. Result: **10 of 12 L0 cells pass**; the two failures (short|day|inter, mid|day|inter) were not rescuable at L1/L2 (rescue levels caught nothing because the failing legs re-pool into already-passing patterns). Only **340 training legs (1.8%) are unsupported** → excluded from all recommendations. The A1 redesign worked: profile overlap covers 98.2% of legs vs the 574 legs (3%) the dead exact-corridor design would have used.

## Finding 1 — FTL runs a better delay ratio in 9 of 10 supported profiles

Within-cell median delay ratio (training, observational — route type is *chosen*, selection on unobservables possible): FTL beats Carting everywhere except mid|night|inter (1.83 vs 1.74). Largest gaps: short|day|intra (2.05 vs 2.61), long|day|inter (1.91 vs 2.47), short|night|inter (1.82 vs 2.30). Chart: `route_framework.png`.

## Finding 2 — raw minutes mislead; the ratio gap is the honest time input

Raw within-cell minute deltas say Carting is "faster" on long cells (e.g., long|day|inter: −228 min) — an artifact: FTL runs longer distances *within* the same tercile. Holding distance fixed (dt\* = ratio gap × cell median OSRM time), Carting costs **+117 min on long|day|inter, +83 on long|night|inter, +23 on long|day|intra**, and single-digit-to-+12 min on mid/short cells. dt\* is the break-even's time input; dt_raw is shown in the CSV for contrast.

## Finding 3 — the M3 counterfactual is unusable, and that's reported, not papered over

Scoring test legs with route_type flipped moves M3's predictions by ~0.0 min in every cell: corridor/node delay history makes route_type informationally redundant to the model. Consequence (stated in output and carried to the memo): **the registered counterfactual instrument fails on this dataset**; the framework's time input is the observational within-cell ratio gap. This also corroborates step 4's A3 verdict — the model leans on corridor history, not on route-type structure.

## Break-even (all three constants are dials — no cost data exists)

V\* = (C_F − v·dt\*)/c_c with dials C_F = ₹18,000/FTL trip, c_c = ₹9/kg Carting, v = ₹2/min. The volume term dominates (C_F/c_c = 2,000 kg); the measured time penalty shifts V\* by at most ~26 kg (long|day|inter). **Honest conclusion for the memo: at any plausible delay valuation, the FTL/Carting choice is a volume-economics decision, not a delay decision — except on long daytime corridors, where Carting's ~2-hour distance-adjusted penalty argues for FTL above ~half-load.** Dials exposed in the CSV; the memo presents the formula, not a fake precision number.

## Corroborating exhibit (registered as too thin to carry weight)

The 14 exact-overlap training corridors: FTL has the lower median ratio on 7 of 14 — a coin flip at this sample size, consistent with "exact-corridor comparison has no power here" (the reason A1 exists).

## Caveats carried forward

- Observational throughout; "FTL is faster" means "legs Delhivery chose to run FTL ran better ratios within profile" — no causal claim.
- mid|night|inter (the one Carting win) has the FTL-thinnest support (184 legs) — noted, not over-read.
- Counterfactual failure means route-shift recommendations in the memo rest on the observational gaps + the volume economics, stated as such.
