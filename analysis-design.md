# P4 Analysis Design (pre-registered before any outcome mining)

**Date:** 2026-06-11
**Status:** registered BEFORE any delay-vs-feature relationship was examined. The probe (`data-probe-findings.md`) covered structure/quality/yield only; the one outcome-adjacent number seen is the marginal delay-ratio distribution (D1), which was needed to test the brief's own threshold. Changing anything below after seeing feature-outcome relationships demotes the result from confirmatory to exploratory and must be disclosed.
**Skills applied:** beyond-ai (4-layer escalation), data-scientist (8-step loop), ground-truth-claims (probe citations A–F refer to `probe-report.txt`).

## 1. The default solution, named and killed

The AI-average submission for this brief: load the CSV, build a NetworkX graph on all rows, compute betweenness/degree/clustering, run node2vec on the full graph, feed embeddings + trip features to XGBoost, beat a linear-regression baseline on MAE, call the top-5 betweenness nodes "bottlenecks," and write a memo saying "upgrade these hubs." Anyone with ChatGPT and this Kaggle-circulated CSV produces exactly this. It fails on this specific dataset, not just on taste:

- **It leaks.** The provided split is temporal (E3: train Sep 12–26, test Sep 27–Oct 3, zero trip overlap). Corridor medians, centralities, and embeddings computed on the full graph carry test-period outcomes into the features. The brief's own line — "the graph advantage must be measured, not claimed" — is failed silently, with inflated numbers.
- **Its bottleneck list is noise.** The brief's ">20% over OSRM = chronically delayed" flags 94.8% of legs (D1) because OSRM models drive time and actual time includes handling. Ranking corridors by raw mean factor surfaces 1-observation corridors with ratio 77 (D1 max), not operational chokepoints.
- **Its baseline is a straw man.** A weak baseline (trip features without `osrm_time`) makes any graph model look good. The graph advantage is only real against a strong tabular baseline that already knows OSRM's estimate, route type, hour, and distance.
- **Unweighted betweenness finds geometric middlemen, not chokepoints.** On a 22-day sampled subgraph (1,657 nodes, C1) topological centrality ranks map position; operations care about flow-weighted position — how many actual shipments cross the node.

## 2. Estimand and architecture

**Estimand (one sentence):** for a delivery leg dispatched on corridor (A→B) with known route type, hour, and OSRM estimate, what is the actual transit time, predicted using only information available before dispatch and only from the training period (Sep 12–26)?

Prediction question, associational. The FTL-vs-Carting framework (section 6) is the only place a treatment-flavored question appears, and it gets an explicit observational caveat plus an overlap design — no causal claims from raw comparisons.

**Unit of analysis: the leg** (one corridor traversal; 26,369 under the corrected 4-part key, probe §5.1), modeled at leg level and additionally evaluated at trip level (sum of leg predictions vs realized trip time) because trips are what an ops leader quotes. Ground truth per leg = max cumulative `actual_time` row (max, not last, to survive the 20 scan-sequence-broken legs).

**Split protocol:** the provided `data` column is honored as the single train/test boundary. Every learned artifact — corridor aggregates, centralities, embeddings, encoders, imputers — is fit on training legs only. Model selection via temporal sub-split inside training (last ~3 days as validation), never via test peeking. Test is touched once per final model.

**Evaluation (pre-specified, both grains):**
- MAE and the brief's business metric: % of predictions within 15% of actual.
- Reported **split by corridor seen/unseen in training** (15.2% of test corridors are cold-start, E3) — the segment where graph structure should genuinely earn its keep.
- Uncertainty: cluster bootstrap by corridor (legs within a corridor are dependent; i.i.d. bootstrap would understate intervals).

## 3. Pre-registered model contest

| ID | Model | Features | Role |
|---|---|---|---|
| M0 | OSRM as-is | predicted = `osrm_time` | The incumbent the brief attacks; every claim is relative to this |
| M1 | Corridor lookup | training-period corridor median ratio × osrm_time, hierarchical fallback | The "is ML even needed?" baseline |
| M2 | Strong tabular | gradient boosting on osrm_time, osrm_distance, route type, hour bucket, day-of-week, source/dest state, corridor aggregates (train-only) | The honest non-graph ceiling |
| M3 | M2 + graph features | M2 + node centralities (flow-weighted), node2vec embeddings of source/dest, neighborhood delay aggregates — all from the training-period graph | The brief's required graph model |

*(M2/M3 feature boundary and the "demonstrable" criterion amended pre-execution — see §9 A2/A3.)*

**The graph advantage = M3 − M2, same learner, same protocol** — an ablation, not a learner shoot-out. Pre-registered honesty clause (P2/P3 precedent): if M3 ≤ M2 on test MAE, that is the reported finding, with the cold-start segment examined as the most plausible place graph features still help. GraphSAGE is attempted only if the PyTorch-Geometric toolchain installs cleanly on this Windows machine; node2vec is the registered primary (library APIs to be verified via Context7 at build time, not from memory).

**The leak experiment (house method, P3 step 3):** M3 trained twice — once with full-data graph artifacts (the default solution's silent error), once with train-only artifacts. Both test MAEs reported: "graph leakage flatters MAE by X minutes / Y%" converts the brief's top criterion into a measured result.

## 4. Bottleneck audit definitions (pre-registered before computing any ranking)

1. **Chronic-delay corridor** (replaces the brief's >20% rule, which D1 shows flags 94.8% of legs): corridor's shrunken median delay ratio in the **top decile of the corridor distribution**, with ≥5 training observations (58.6% of corridors, 91.7% of legs, C2). Shrinkage: empirical-Bayes pull of corridor medians toward the route-type median, weight ∝ observation count — small-area-estimation discipline imported so 1-obs corridors can't top the table. Deviation from the brief documented with D1 as evidence. *(Shrinkage constant pinned pre-execution — see §9 A4.)*
2. **Bottleneck hub:** composite of (a) flow-weighted betweenness (edge weights = observed leg counts; weighted by what actually moves, not topology) *(implementation pinned in §9 A5 — the naive networkx call computes the wrong thing)*, (b) total excess minutes attributable to incident corridors (Σ legs × (actual − OSRM) on edges touching the node), (c) dwell proxy = od-window duration minus driving time on legs originating there (D4 gap). Ranked by (b) for the memo — excess minutes are what an ops leader can buy back; (a) and (c) explain *why*.
3. **SLA proxy (no SLA column exists):** promised time = OSRM × network median ratio (the calibration Delhivery would trivially apply); breach = actual > promised × 1.2. Stated in the memo as a constructed assumption with sensitivity to the multiplier.
4. **Revenue at risk:** no revenue column exists. Priced transparently: breached legs × assumed shipment value × assumed penalty/churn fraction, INR-denominated, both assumptions stated as dials in the memo with a sensitivity row — never presented as data.

## 5. ETA-as-promise reframe (the consulting edge)

A point MAE is a data scientist's metric; an ops leader promises a time and eats the cost asymmetry — a late delivery costs an SLA breach, an early one costs nothing but slack capacity. Airlines solved this decades ago with block-time padding: publish the p80–p85 of realized time, not the mean [from training — foundational practice, flagged for currency check during report writing]. Deliverable therefore includes **quantile ETAs** (p50/p80/p90 via quantile gradient boosting) and frames the promise level as a business dial: "promise p80 and breach 20% by construction; promise p90 and breach 10% at the cost of X% longer quoted times" — computed per corridor profile. This converts Task 3's model into Task 5's decision instrument, which is the connection the brief hints at ("translate findings into decisions") but the default solution never makes.

## 6. FTL vs Carting framework (registered design — SUPERSEDED by §9 A1; original kept for the audit trail)

Route type is a *choice*, not an assignment: raw FTL-vs-Carting comparisons are confounded by corridor selection (FTL runs different corridors than Carting, C3). Registered design:

1. Identify **overlap corridors** — those served by both route types in training (count to be established at build time; existence implied by C3's separate corridor sets summing past the union but verified before use).
2. Within-corridor comparison of delay ratio and absolute time on the overlap set = the cleanest available estimate of the route-type effect, explicitly labeled "observational, selection on unobservables possible."
3. The decision framework is then a predicted-time-under-both-types model (M3 scored counterfactually with route type flipped) **only on corridor profiles inside the overlap support** — no extrapolated recommendations where one type was never observed.
4. Cost side: FTL vs Carting cost-per-kg assumptions stated as dials (no cost data exists), framework outputs a break-even shipment volume per corridor profile.

## 7. Second-order effects (registered before building)

- **Goodhart on the chronic-corridor list:** once corridors are ranked, regional managers can game the metric by re-routing volume off measured corridors. Mitigation stated in memo: re-rank quarterly, monitor network-level total excess minutes (ungameable aggregate), not just the named-corridor list.
- **Padding erodes the product:** if quantile promises are adopted, quoted ETAs lengthen on bad corridors; sales loses a competitive number. The memo must present the promise dial as a pricing/positioning decision, not a free win — who loses: sales teams quoting against competitors' optimistic ETAs.
- **Hub-upgrade displacement:** fixing the top hub re-routes flow and can move the bottleneck downstream (queueing networks shift, they don't vanish). The memo's upgrade quantification is first-order and says so; a re-simulation after re-routing is named as the follow-up, not silently promised.
- **22-day window:** September–October 2018, pre-festival-season. Volume spikes (Diwali) are exactly when bottlenecks bind hardest and are unobserved. Every memo number carries "steady-state, non-peak" scope.

## 8. Origin statement (Layer 4)

What a competitor with the same prompt does not produce: (a) the D1 finding that the brief's own 20% threshold flags 94.8% of the network — discovered by auditing before modeling, and the justification for the shrinkage-based chronic-corridor definition; (b) the train-period-only graph discipline plus the leak experiment quantifying what everyone else's full-graph embeddings silently gain; (c) the ETA-as-promise quantile reframe importing airline block-time practice into parcel logistics; (d) the FTL/Carting overlap design (profile-level per §9 A1, after the exact-corridor version was killed by its own support count) that refuses the confounded global comparison the data invites; (e) M3−M2 ablation with a same-learner protocol so "graph advantage" is measured, as the brief demands, not claimed.

## 9. Amendments (2026-06-11, registered pre-Step-2)

Adopted after an adversarial review of the registered design (case-judge Judge mode, same session as registration), BEFORE any Step-2+ code ran and before any delay-vs-feature relationship was mined. The only new data consulted: a count of FTL/Carting overlap corridors (A1 evidence), which is feature-side structure, not an outcome relationship. Original text above is preserved; where conflicting, these amendments govern.

**A1 — FTL vs Carting redesigned to profile-level overlap (supersedes §6.1–6.3).**
Evidence: exact-corridor overlap is 23 corridors in all data, **14 in training, 574 legs** (counted from `data/clean/legs.csv` this session) — far too thin for within-corridor estimation; the registered design fails its own support requirement. Amended design: overlap is defined at the **corridor-profile** level — (osrm_distance training-tercile) × (dispatch window: 06:00–18:00 vs 18:00–06:00) × (intra-state vs inter-state), 12 cells. A cell enters the comparison only with ≥30 training legs of EACH route type; thinner cells merge along a pre-stated order (first collapse dispatch window, then distance tercile to halves). The exact-corridor comparison (14 corridors) is reported only as a corroborating exhibit. Counterfactual route-type scoring is restricted to supported cells. The observational caveat strengthens accordingly: at profile level, "FTL corridors differ in unmeasured ways" is a live objection the memo must state, not a footnote.

**A2 — M2/M3 feature boundary sharpened so M3−M2 measures structure, not identity (amends §3 table).**
As registered, M2 lacked node-level features, so M3's embeddings could "win" merely by encoding node identity (which facility this is) — information a plain categorical/aggregate feature carries without any graph. Amended boundary: **M2 additionally gets node-level train-only aggregates** (source/dest center mean & median delay ratio, leg counts). **M3 adds only structural information**: centralities, node2vec embeddings, 1-hop neighborhood delay aggregates (neighbors' delay stats, excluding the node's own corridors). M3−M2 is then an honest estimate of what network *position* contributes beyond what the facility's own history tells you.

**A3 — "Demonstrable" pre-defined + trip-grain ground truth pinned (amends §2/§3).**
(a) The graph advantage is *demonstrable* iff the 95% corridor-cluster-bootstrap CI of MAE(M2)−MAE(M3) on test excludes zero — evaluated separately overall and on the cold-start (unseen-corridor) subset. Anything else is reported as "no demonstrable advantage" regardless of the point estimate's sign. (b) Trip-grain primary ground truth = **sum of leg transit times** (apples-to-apples: M0's trip prediction is the sum of leg OSRM times, and no contest model predicts hub dwell). End-to-end elapsed time (last od_end − first od_start) is reported as a separate exhibit with the dwell gap explicitly attributed — it connects the model section to the bottleneck audit's dwell finding rather than contaminating the contest.

**A4 — Shrinkage constant pinned (amends §4.1).**
Shrunken corridor ratio = (n·corridor_median + κ·route_type_median)/(n + κ) with **κ = median observations per training corridor**, computed once in `02_graph.py` and logged before any ranking is produced. κ is a data-determined constant fixed by formula, not tuned; sensitivity of the top-10 corridor list to κ/2 and 2κ goes in the audit appendix.

**A5 — Betweenness implementation pinned + seeds (amends §4.2, adds to protocol).**
networkx `betweenness_centrality` interprets edge weights as shortest-path COSTS, not volumes [from training; API verified via Context7 before `02_graph.py` is written] — passing flow counts as weights computes nonsense. Two metrics, both reported: (i) the brief's betweenness, computed with edge cost = median actual minutes (time-weighted shortest paths); (ii) **observed throughput** = count of training trips whose leg sequence passes through the node as an intermediate stop (destination of leg k = source of leg k+1). Divergence between (i) and (ii) is reported as a finding (topological vs operational importance). All stochastic steps (node2vec walks, GBM subsampling, bootstrap) run with fixed, logged seeds recorded in model-log.md.
