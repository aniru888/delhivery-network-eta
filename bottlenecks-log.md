# P4 Bottleneck Audit Log (step 3)

**Date:** 2026-06-11
**Script:** `scripts/03_bottlenecks.py` → `outputs/chronic_corridors.csv` (145), `outputs/hub_ranking.csv` (1,590), 3 charts. Training legs only (18,948, asserted). All numbers from this session's run. Definitions executed exactly as registered (analysis-design.md §4, amendments §9); seed=42, B=1000 per A5.

## SLA proxy (registered §4.3)

- Calibration: network median delay ratio = **2.000** (training) → promised = OSRM × 2.0; breach = actual > promised × 1.2.
- Breach rate at 1.2 margin: **30.3%** of training legs.
- Sensitivity (the dial, charted in `sla_sensitivity.png`): margin 1.0× → 49.3% breach; 1.1× → 38.7%; 1.2× → 30.3%; 1.3× → 24.4%; 1.5× → 16.4%. Every breach number downstream inherits this constructed constant — the memo presents it as a policy dial.

## Chronic corridors (registered §4.1 + A4)

- Eligible (≥5 train obs): 1,447 of 2,508 corridors. Top-decile shrunk-ratio cut = **2.740** → **145 chronic corridors**, ranked by SLA-breach contribution (brief task 2).
- **Finding — chronic delay is an intra-city Carting phenomenon:** the chronic list is 93% intra-state and 68% Carting, vs 83% / 40% in the eligible pool. The entire top-10 is Carting, and visibly intra-city (Mumbai Hub → MiraRd/CottonGreen, Kolkata Dankuni → Beliaghata/Tiljala, Hyderabad Alwal → Shamshabad). Long-haul FTL is not where the worst ratios live.
- **Finding — chronic means chronic:** per-corridor breach rate on the list: median **100%**, min 50%. The 12 worst breach on 69–100% of their runs (`chronic_corridors.png`) — structural, not bad luck.

## Hub ranking by excess minutes (registered §4.2b)

Attribution note (logged): a leg's excess counts toward BOTH endpoints — valid for ranking, NOT additive across hubs; "top-5 touch 30.0% of endpoint-attributed excess" uses the 2× denominator accordingly. Network total excess (actual − OSRM, training): **34,937 hours over 15 days**.

| # | Hub | Excess min | Breached legs | Betweenness | Throughput | Dwell med (min) | Bootstrap top-5 % |
|---|---|---|---|---|---|---|---|
| 1 | Gurgaon_Bilaspur_HB | 509,741 | 268 | 0.199 | 86 | 151 | **100.0** |
| 2 | Bangalore_Nelmngla_H | 258,345 | 140 | 0.091 | 27 | 141 | **98.1** |
| 3 | Bhiwandi_Mankoli_HB | 222,246 | 399 | 0.050 | 7 | 144 | **99.0** |
| 4 | Kolkata_Dankuni_HB | 146,005 | 218 | 0.096 | 2 | 105 | 68.5 |
| 5 | Hyderabad_Shamshbd_H | 122,948 | 130 | 0.114 | 3 | 152 | 49.3 |
| 6 | Pune_Tathawde_H | 121,814 | 156 | 0.100 | 30 | 113 | — |

## Stability gate: FAIL on ranks 4–5 — reported, not hidden

Registered gate: every top-5 hub persists in ≥80% of corridor-cluster bootstrap resamples. Result: top-3 are rock-solid (100% / 98.1% / 99.0%); **Kolkata_Dankuni 68.5% and Hyderabad_Shamshbd 49.3% FAIL** — ranks 4–6 are a statistical tie (Hyderabad 122,948 vs Pune 121,814 excess minutes, 0.9% apart). Registered handling applies: the memo names the stable top-3 with full confidence and presents ranks 4–6 as an interchangeable tier, sized accordingly. This is the honesty clause doing its job — most teams will print a falsely precise top-5.

## Secondary finding — Bhiwandi_Mankoli is a different kind of bottleneck

Rank 3 by excess minutes and #1 by breached legs (399), yet throughput 7 and betweenness 0.050 — it is a high-volume *endpoint* hub, not a pass-through chokepoint like Gurgaon_Bilaspur (throughput 86, betweenness 0.199). Intervention type differs: terminal capacity/dwell at Bhiwandi vs corridor/transit fixes at Gurgaon. Dwell medians run 105–152 min across the whole top tier — dwell is a network-wide constant, not a single hub's disease.

## Chart inventory (titles carry the insight, per repo rule 5)

1. `bottleneck_map.png` — "5 hubs touch 30% of network excess delay; 145 chronic corridors concentrate the worst ratios" (numbered hubs + legend).
2. `sla_sensitivity.png` — breach rate 49%→16% across margins; the constant is a dial.
3. `chronic_corridors.png` — the 12 worst corridors breach on 69–100% of runs.

## Carried to step 6 (memo)

- Stable top-3 hub names + the 4–6 tie, with the attribution and recoverable-fraction caveats (execution-plan step 6).
- Chronic = intra-city Carting concentration → intervention class is city-distribution operations, not line-haul.
- All breach numbers conditional on the SLA dial; sensitivity row mandatory.
