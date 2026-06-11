"""P4 step 1: scan rows -> canonical leg table.

Executes the decisions registered in analysis-design.md section 2 and
execution-plan.md step 1. Every transformation gets a numbered entry in
cleaning-log.md (written by hand from this script's output); every gate is
a hard assertion - the script dies loudly rather than degrade (Rule 2).

Leg key:     (trip_uuid, source_center, destination_center, od_start_time)
Ground truth: MAX cumulative actual_time per leg (== last for the 99.9% of
              monotonic legs; repairs the 20 scan-sequence-broken legs).
Banned at the door (target-derived, probe D2/D3): factor, segment_factor,
              start_scan_to_end_scan.

Run:  python scripts/01_clean.py   (from the project folder)
Output: data/clean/legs.csv + stdout audit trail.
"""

import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
DATA = os.path.join(PROJ, "data")
OUT = os.path.join(DATA, "clean")
os.makedirs(OUT, exist_ok=True)

LEG_KEY = ["trip_uuid", "source_center", "destination_center", "od_start_time"]

df = pd.read_csv(os.path.join(DATA, "delivery_data.csv"))
print(f"[load] {len(df)} scan rows")

# E1: banned target-derived columns never enter the pipeline
df = df.drop(columns=["factor", "segment_factor", "start_scan_to_end_scan",
                      "cutoff_factor", "cutoff_timestamp", "is_cutoff"])
print("[E1] dropped target-derived columns (factor, segment_factor, "
      "start_scan_to_end_scan) + opaque cutoff fields (probe section 5.2)")

# E2: 1:1 code->name map from non-null rows, backfill the ~0.2% null names
src_map = (df.dropna(subset=["source_name"])
           .drop_duplicates("source_center")
           .set_index("source_center")["source_name"])
dst_map = (df.dropna(subset=["destination_name"])
           .drop_duplicates("destination_center")
           .set_index("destination_center")["destination_name"])
name_map = pd.concat([src_map, dst_map]).groupby(level=0).first()
n_src_null = df["source_name"].isna().sum()
n_dst_null = df["destination_name"].isna().sum()
df["source_name"] = df["source_name"].fillna(df["source_center"].map(name_map))
df["destination_name"] = df["destination_name"].fillna(df["destination_center"].map(name_map))
print(f"[E2] name backfill: source {n_src_null} -> {df['source_name'].isna().sum()} nulls, "
      f"destination {n_dst_null} -> {df['destination_name'].isna().sum()} nulls "
      f"(residual = codes with no named row anywhere)")

# E3: aggregate scan rows -> legs. Cumulative fields take MAX (repairs the 20
# scan-sequence-broken legs; identical to last() on monotonic legs).
mono = (df.groupby(LEG_KEY, sort=False)["actual_time"]
        .apply(lambda s: s.is_monotonic_increasing))
broken = mono[~mono]
print(f"[E3] legs with non-monotonic cumulative actual_time (max-repair applies): "
      f"{len(broken)}")
for key in broken.index:
    sub = df[(df["trip_uuid"] == key[0]) & (df["source_center"] == key[1])
             & (df["destination_center"] == key[2]) & (df["od_start_time"] == key[3])]
    print(f"    {key[0]} {key[1]}->{key[2]}: cumulative sequence "
          f"{sub['actual_time'].tolist()} -> repaired total {sub['actual_time'].max()}")

legs = (df.groupby(LEG_KEY, sort=False)
        .agg(route_type=("route_type", "first"),
             data=("data", "first"),
             od_end_time=("od_end_time", "first"),
             actual_time=("actual_time", "max"),
             osrm_time=("osrm_time", "max"),
             osrm_distance=("osrm_distance", "max"),
             source_name=("source_name", "first"),
             destination_name=("destination_name", "first"),
             n_scan_rows=("actual_time", "size"))
        .reset_index())
print(f"[E3] legs built: {len(legs)}")

# E4: dispatch-context features (available pre-dispatch) + outcome-side audit col
ods = pd.to_datetime(legs["od_start_time"])
ode = pd.to_datetime(legs["od_end_time"])
legs["dispatch_hour"] = ods.dt.hour
legs["dispatch_dow"] = ods.dt.dayofweek
legs["od_duration_min"] = (ode - ods).dt.total_seconds() / 60  # OUTCOME-SIDE:
# dwell-proxy ingredient for the step-3 audit (probe D4). Never a model feature.
legs = legs.drop(columns=["od_end_time"])

# E5: state from the verified "(State)" name suffix (probe C5: 100% parseable)
legs["source_state"] = legs["source_name"].str.extract(r"\(([^)]+)\)\s*$")[0]
legs["dest_state"] = legs["destination_name"].str.extract(r"\(([^)]+)\)\s*$")[0]
print(f"[E5] state parse: source null {legs['source_state'].isna().sum()}, "
      f"dest null {legs['dest_state'].isna().sum()} "
      f"(equals residual unnamed codes from E2)")

# ------------------------------------------------------------------- GATES
# G1: exact leg count, verified against the probe session (probe section 5.1)
assert len(legs) == 26369, f"GATE G1 FAILED: {len(legs)} legs, expected 26369"
# G2: scan-row conservation
assert legs["n_scan_rows"].sum() == 144867, "GATE G2 FAILED: scan rows lost"
# G3: target sanity (probe D1: none exist; enforce, don't trust)
assert (legs["actual_time"] > 0).all(), "GATE G3 FAILED: nonpositive actual_time"
assert (legs["osrm_time"] > 0).all(), "GATE G3 FAILED: nonpositive osrm_time"
# G4: split integrity - no trip straddles train/test (probe E3)
straddle = legs.groupby("trip_uuid")["data"].nunique()
assert (straddle == 1).all(), "GATE G4 FAILED: trip in both splits"
# G5: key uniqueness
assert not legs.duplicated(LEG_KEY).any(), "GATE G5 FAILED: duplicate leg keys"
# G6: every leg has route_type and timestamps parsed
assert legs["route_type"].isin(["FTL", "Carting"]).all(), "GATE G6 FAILED: route_type"
assert legs["dispatch_hour"].notna().all(), "GATE G6 FAILED: unparsed od_start_time"
print("[gates] G1 leg count 26,369 | G2 row conservation 144,867 | G3 positive targets "
      "| G4 split integrity | G5 key uniqueness | G6 dispatch context -- ALL PASS")

out_path = os.path.join(OUT, "legs.csv")
legs.to_csv(out_path, index=False)
print(f"[saved] {out_path}  ({len(legs)} legs x {legs.shape[1]} cols)")
print("split counts:", legs["data"].value_counts().to_dict())
print("route_type counts:", legs["route_type"].value_counts().to_dict())
