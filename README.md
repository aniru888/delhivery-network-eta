# P4 — Delhivery Graph ETA Optimization

Solution to "Optimizing Delivery ETAs with Graph-Based Network Intelligence" (Summer Projects '26, C&A Club IIT Guwahati). Built 2026-06-11.

**Live dashboard:** https://delhivery-network-eta.streamlit.app

Grader-facing deliverables: `technical-report.pdf` (4 pages, method + findings + exhibits), `network-ops-memo.pdf` (2 pages, for the ops leader), and the dashboard (run locally with):

```
streamlit run app/network_console.py     # from this folder
```

## Reproduce

```
python scripts/00_probe.py            # structure audit  -> probe-report.txt
python scripts/01_clean.py            # scan rows -> data/clean/legs.csv (26,369 legs, 6 gates)
python scripts/02_graph.py            # train-only graph -> corridor_agg.csv, node_metrics.csv
python scripts/03_bottlenecks.py      # chronic corridors + hub ranking + charts -> outputs/
python scripts/04_model.py            # M0-M3 contest + leak experiment + quantiles -> outputs/
python scripts/05_route_framework.py  # FTL/Carting profile framework -> outputs/
```

**Data:** the raw `data/delivery_data.csv` (53 MB, 144,867 rows) is not committed — download it from the dataset link distributed with the problem statement ([Google Drive](https://drive.google.com/file/d/1XshXPF33sf2E6yRKfze5k-tfVo0jHgPE/view?usp=sharing)) and place it at `data/delivery_data.csv` before running scripts 00–01. All derived artifacts (`data/clean/`, `outputs/`) ARE committed, so the dashboard and scripts 02–05 run without the raw file. The problem-statement files are omitted from this public repo (club material with personal contact details).

**Reproducibility verified 2026-06-11:** cold re-run of 01→05 reproduces all 8 output CSVs **bit-for-bit** (MD5-identical; snapshot in `outputs/_hashes_before.txt`). All stochastic steps are seeded (seed 42). Exception: `scripts/04a_embeddings.py` (node2vec) needs a temporary `pip install node2vec gensim` — gensim pins numpy<2 and conflicts with this machine's numpy 2.4.4, so the protocol is install → run once (PYTHONHASHSEED=0) → uninstall → restore numpy. Its outputs (`data/clean/emb_train.csv`, `emb_full.csv`) are committed artifacts consumed by 04/05.

## Method documents (read in this order)

| Doc | What it is |
|---|---|
| `data-probe-findings.md` | Pre-plan structure audit; every claim cites `probe-report.txt` section |
| `analysis-design.md` | **Pre-registered** design (before outcome mining) + §9 amendments A1–A5 (registered pre-Step-2 after adversarial self-review) |
| `execution-plan.md` | 8 steps, each with a verification gate |
| `cleaning-log.md`, `graph-log.md`, `bottlenecks-log.md`, `model-log.md`, `route-framework-log.md` | Per-step decisions, gates, findings — all numbers from run output |

## Headline results

| Model (test = last 7 days, touched once) | Leg MAE (min) | within ±15% |
|---|---|---|
| OSRM as-is (incumbent) | 107.4 | 4.5% |
| Corridor calibration table (M1) | 35.8 | 47.4% |
| Strong tabular GBM (M2) | 34.4 | 53.3% |
| M2 + graph features (M3) | 34.4 | 53.7% |
| M3 with leaked full-data graph | 25.1 | 61.4% |

- **Graph advantage: NOT demonstrable** (pre-registered criterion: 95% corridor-cluster bootstrap CI of MAE(M2)−MAE(M3) excludes zero; observed CI [−0.28, +0.14]).
- **The leak experiment is the differentiator:** computing graph artifacts on train+test (what a team without temporal discipline ships) flatters MAE by 27.1% — the "graph advantage" others will claim is quantified contamination.
- **Bottlenecks:** top-3 hubs statistically stable under bootstrap (Gurgaon Bilaspur, Bangalore Nelmangala, Bhiwandi Mankoli); ranks 4–6 a tie — reported as such. 145 chronic corridors are 93% intra-state, 68% Carting (city shuttles, not line-haul).
- **Brief deviation, evidenced:** the brief's ">20% over OSRM = chronically delayed" flags 94.8% of legs (median ratio = 2.0); replaced with top-decile shrunken corridor ratio (κ-shrinkage, ≥5 obs), documented in `analysis-design.md` §4.

## Submission checklist mapping (brief)

1. Documented code: `scripts/00–05` + per-step logs (this file = run order)
2. Graph visualizations: `outputs/bottleneck_map.png`, `chronic_corridors.png`, `sla_sensitivity.png`, `route_framework.png`
3. Model comparison (MAE + 15% business metric): `outputs/model_comparison.csv` + `model-log.md`
4. FTL vs Carting framework: `outputs/route_framework.csv` + `route-framework-log.md`
5. Strategy memo: `network-ops-memo.pdf` (2 pages)
6. Streamlit dashboard: `app/network_console.py` — Network / Hubs / Quote-an-ETA / Evidence tabs, live SLA + promise dials; design system `~/.claude/design-systems/custom/delhivery-network-ops.md`; AppTest-verified (0 exceptions incl. widget interactions)

## Assumptions register (everything not in the data)

| Assumption | Where used | Dial value |
|---|---|---|
| SLA promise = OSRM × network median ratio (2.0), breach margin 1.2× | breach counts everywhere | sensitivity 1.0–1.5× shown |
| FTL cost/trip, Carting ₹/kg, ₹/min delay value | break-even V* | ₹18,000 / ₹9 / ₹2 |
| Recoverable fraction f of hub-attributed excess | memo impact table | 20–40% range, to be set by time-study |
| `actual_time` semantics (transit incl. partial dwell) | everywhere | inferred from probe D4, not documented in source |
