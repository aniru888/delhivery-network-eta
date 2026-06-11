# Network Operations Strategy Memo — ETA Reliability & Bottleneck Action Plan

**To:** Head of Network Operations · **Basis:** 14,817 trips / 26,369 corridor legs, Sep 12 – Oct 3, 2018 · **Scope:** steady-state, non-peak (no festival-season data); all findings re-verified by full pipeline re-run

---

## Three decisions, in priority order

1. **Stop quoting raw OSRM times — deploy the corridor calibration table this quarter.** OSRM misses the true transit time by 107 minutes per leg on average; only 4.5% of legs land within 15% of it. A simple table — each corridor's historical actual-vs-OSRM multiplier — cuts that error to 36 minutes (47% within 15%) with no model, no infrastructure. The full prediction model adds only ~2 minutes more (54% within 15%): **the table is 95% of the win and can ship in weeks.**
2. **Quote the 80th-percentile time, not the average.** Today a median quote of 75 minutes is kept roughly half the time. Quoting 90 minutes (the p80 figure from the same data) is kept ~80% of the time — verified out-of-sample at 78%. The 15-minute longer quote is a pricing/positioning choice; the breach-rate drop is measured, not modeled.
3. **Fix three hubs and twelve city corridors — not a top-five list.** Three hubs are statistically solid bottlenecks (they survive 98–100% of resampling checks); ranks 4–6 are a tie and should be treated as one watch-tier. Legs touching the top three carry **39% of all network excess hours** (13,708 of 34,937 hours over 15 days) while being only 17.8% of legs.

## The three hubs — and why they need different fixes

| Hub | Excess hours /day touching it | Late legs /day | Median dwell | Diagnosis → intervention |
|---|---|---|---|---|
| Gurgaon Bilaspur HB | ~566 (network #1) | 18 | 2.5 h | Pass-through chokepoint (most through-traffic in network). Sortation/cross-dock capacity + parallel routing for trips that don't terminate there |
| Bhiwandi Mankoli HB | ~247 | 27 (network #1 in breaches) | 2.4 h | Volume terminal, almost no through-traffic. Dock scheduling + unload capacity, not routing |
| Bangalore Nelmangala H | ~287 | 9 | 2.4 h | Mixed profile. Dwell reduction first; ~2.4 h median dwell is the binding constraint |

Dwell of ~2.4–2.5 hours per leg-start is near-uniform across all top hubs — handling time, not driving, is where the schedule dies.

## The corridor problem is inside cities, not between them

Of 145 chronically delayed corridors (worst-decile delay ratios, min. 5 observations), **93% are intra-state and 68% are Carting** — short urban shuttle runs, not line-haul. The twelve worst breach their promise on **69–100% of runs** — e.g., Mumbai Hub→Mira Road late 31 of 45 runs, Hyderabad Chikkadpally→Shamshabad late 22 of 22. This is structural, so it is fixable: dispatch-window changes and load consolidation on ~12 named corridors, not a network-wide program.

**Route-type rule:** on comparable runs, FTL beats Carting's delay ratio in 9 of 10 corridor profiles; distance-adjusted, Carting costs up to ~2 extra hours on long daytime corridors. At plausible costs the choice stays volume-driven (break-even ≈ FTL trip cost ÷ Carting per-kg rate ≈ 2,000 kg at our dial settings) — **except long daytime corridors, where the delay penalty justifies FTL from about half-load.**

## What the top-3 fix is worth (formula + dials, not invented precision)

Measured: 914 excess hours/day and 54 late legs/day (14% of all breaches) touch the top-3 hubs. Not in this dataset: shipment value, SLA penalties, recoverable share of handling time. Impact therefore comes as a formula with the dials exposed:

| Quantity | Formula | Conservative (f=20%) | Ambitious (f=40%) |
|---|---|---|---|
| Hours recovered /day | f × 914 | 183 h | 366 h |
| Late deliveries avoided | f × 14% of breaches | −2.8% network late rate | −5.6% |
| Revenue at risk recovered /day | f × 54 legs × value × at-risk% | ₹54k @ ₹10k/leg, 50% at-risk | ₹108k |

f = the share of hub-attributed excess an upgrade actually removes — set it from a 2-week dwell time-study, not from this memo. Excess time vs OSRM partly reflects unavoidable handling; claiming all 914 hours would be dishonest.

## 90-day plan

| When | Action | Owner | Success measure |
|---|---|---|---|
| Wks 1–4 | Calibration table live in quoting; p80 quotes A/B on 2 regions | Network planning | Within-15% rate 4.5% → >45%; kept-promise rate ~80% on test regions |
| Wks 2–6 | Dwell time-study at Gurgaon Bilaspur + Bhiwandi Mankoli → sets f AND scopes upgrade cost | Hub ops | Measured f with range + capex estimate per hub |
| Wks 4–10 | Dispatch-window + consolidation pilot on the 12 named city corridors | Regional ops (Mumbai, Kolkata, Hyderabad) | Per-corridor breach rate from 69–100% to <50% |
| Wks 8–12 | FTL shift on long-day corridors above half-load | Line-haul planning | Delay ratio on shifted corridors → FTL baseline (≈1.9) |
| Quarterly | Re-rank hubs/corridors; track network excess hours (the un-gameable total), not just the named list | Analytics | Total excess hours/day trending down |

**Honesty notes, kept short:** all breach figures use a constructed SLA (promise = 2× OSRM, 20% margin; breach rate moves 49%→16% across margins 1.0–1.5×, so treat the absolute level as a dial and the *rankings* as the finding). Comparisons across route types are observational. Data covers 22 non-peak days; festival-season bottlenecks will be worse and are unmeasured.
