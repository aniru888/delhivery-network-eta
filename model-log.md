# P4 Model Log (step 4)

**Date:** 2026-06-11
**Scripts:** `scripts/04a_embeddings.py` (node2vec, run under a temporary gensim install — see Environment note), `scripts/04_model.py` → `outputs/model_comparison.csv`, `outputs/test_predictions.csv`. All numbers from this session's runs. Protocol: analysis-design.md §2–3 + amendments A2/A3/A5, executed as registered. Seeds: 42 everywhere; PYTHONHASHSEED=0 for embeddings; hp2 = {lr 0.05, depth None, iters 400}, hp3 = {lr 0.1, depth 8, iters 200} (selected on the Sep 24–26 temporal validation split, test untouched during selection).

## Headline results (test = Sep 27–Oct 3, 7,421 legs, touched once per final model)

| Model | Leg MAE (min) | Leg ±15% | Trip MAE | Trip ±15% | Seen MAE | Cold MAE |
|---|---|---|---|---|---|---|
| M0 OSRM as-is | 107.39 | 4.5% | 190.90 | 2.7% | 106.53 | 121.30 |
| M1 corridor lookup | 35.75 | 47.4% | 55.57 | 49.0% | 33.36 | **74.38** |
| M2 strong tabular | 34.35 | 53.3% | 53.37 | 54.1% | 28.04 | 136.33 |
| M3 + graph features | 34.41 | 53.7% | 53.48 | 54.0% | 28.14 | 135.82 |
| M3 LEAKY (full-data graph) | **25.10** | 61.4% | — | — | — | — |

Trip grain = sum of leg transit times (A3). Seen/cold split: 6,989 / 432 test legs (15.2% of test *corridors* are cold; they carry fewer legs each).

## A3 verdict: the graph advantage is NOT demonstrable — and that's the result

MAE(M2) − MAE(M3), corridor-cluster bootstrap (B=1,000, seed 42):
- **Overall: −0.06 min, 95% CI [−0.28, +0.14] → includes zero.**
- **Cold-start: +0.54 min, 95% CI [−0.70, +1.98] → includes zero.**

Under the pre-registered criterion, structural graph information (centralities, embeddings, neighbor aggregates) adds nothing measurable beyond what a facility's own delay history already carries (the A2-fortified M2). The registered honesty clause applies: reported plainly, both grains, no post-hoc re-definition of "demonstrable."

## The leak experiment is the submission's centerpiece

M3 retrained with full-data graph artifacts (corridor aggregates, node aggregates, structural metrics, embeddings computed on train+test legs — exactly what a team that skips the temporal discipline ships): **leg MAE 25.10 vs clean 34.41 — leakage flatters MAE by 9.31 min (27.1%) and lifts ±15% accuracy from 53.7% to 61.4%.**

Combined with the A3 result, this licenses a strong claim: *teams reporting a large graph advantage on this dataset are measuring their own leak.* The brief's "the graph advantage must be measured, not claimed" is answered with: measured, absent; the apparent advantage is quantified contamination. (P3 precedent: same experiment design, AUC 0.889 leaky vs 0.660 clean.)

## What actually drives accuracy (consulting translation)

1. **OSRM is not an ETA.** The incumbent misses by 107 min/leg; only 4.5% of legs land within 15%. Nobody should quote raw OSRM.
2. **A lookup table gets ~95% of the achievable gain.** M1 (train-period shrunk corridor ratio × OSRM) cuts MAE 107 → 36. The full ML stack only improves that to 34.4 (+5.9pp on ±15%). The memo's first recommendation is therefore an *operational calibration table*, not a model deployment.
3. **Cold-start inverts the ranking.** On unseen corridors the GBMs collapse (MAE ~136) while M1's route-type fallback holds (74.4) — trees overtrust corridor aggregates that are NaN on cold legs. Operational rule: route cold-start corridors to the multiplier fallback.
4. **Exploratory (constructed after seeing test, labeled as such): routed prediction** (M3 on seen, M1 on cold) = leg MAE 30.83, ±15% 54.5%, trip MAE 47.43. The routing rule is a priori sensible; flagged for confirmation in the report as the deployment design, not a confirmatory result.

## Quantile ETAs (the promise dial, design §5)

| Promise level | Empirical test coverage | Median promised time |
|---|---|---|
| p50 | 55.7% (target 50%) | 75 min |
| p80 | 78.1% (target 80%) | 90 min |
| p90 | 86.6% (target 90%) | 109 min |

p80 is well calibrated out of temporal sample; p90 runs ~3pp under target (tail drift across weeks — noted, usable with a small uplift). The dial for the memo: promising p80 instead of the median lengthens the median quote 75 → 90 min and converts a coin-flip ETA into an ~80%-kept promise.

## Limitations (single compact section, house style)

- Aggregate features include the own leg for training rows (no leave-one-out); test metrics unaffected — cost is training overtrust only.
- node2vec p=q=1 (default walk bias), 32-dim; other parameterizations unexplored (registered primary, not tuned to avoid a search over the test).
- GraphSAGE not attempted: torch-geometric install risk on this machine; registered contingency exercised.
- 22-day window: weekly seasonality at best; no festival-season behavior.
- Cold-start CI is wide (432 legs over 275 corridors) — genuinely underpowered, said as much.

## Environment note (deliberate, reversed, verified)

gensim 4.4.0 pins numpy<2 and pip downgraded numpy 2.4.4 → 1.26.4 during install. Protocol followed: embeddings computed and saved to CSV (`emb_train.csv`, `emb_full.csv`, seeds logged), then gensim/node2vec/smart_open/wrapt removed and numpy 2.4.4 restored; pandas/sklearn/opencv/rasterio imports re-verified afterwards. Reproducing `04a_embeddings.py` requires repeating the temporary install; `04_model.py` needs only sklearn + the CSVs. The pre-existing `pymrio`/openpyxl conflict warning predates this session and was not touched.
