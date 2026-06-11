"""P4 probe: structure / quality / anomaly audit of delivery_data.csv.

Discipline (P3 precedent): NO model-relationship mining. This audit settles
STRUCTURE only — row hierarchy, cumulative-vs-incremental fields, graph node/
edge yield, target integrity — before any analysis design is registered.

Central question this probe must settle empirically (not from dataset folklore):
within a (trip_uuid, source_center, destination_center) group, is actual_time
cumulative while segment_actual_time is incremental? The answer determines the
entire aggregation pipeline.

Run:  python scripts/00_probe.py   (from the project folder)
Output: stdout + probe-report.txt in the project folder.
"""

import io
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
DATA = os.path.join(PROJ, "data")

buf = io.StringIO()


def emit(*args):
    line = " ".join(str(a) for a in args)
    print(line)
    buf.write(line + "\n")


def section(title):
    emit("\n" + "=" * 78)
    emit(title)
    emit("=" * 78)


pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 30)

df = pd.read_csv(os.path.join(DATA, "delivery_data.csv"))

# ---------------------------------------------------------------- A. shapes
section("A. SHAPE / DTYPES / NULLS / EXACT-DUP ROWS")
emit(f"\nshape={df.shape}, exact duplicate rows={df.duplicated().sum()}")
info = pd.DataFrame({"dtype": df.dtypes.astype(str),
                     "nulls": df.isna().sum(),
                     "null_pct": (df.isna().mean() * 100).round(2)})
emit(info.to_string())

# ------------------------------------------------------------ B. hierarchy
section("B. ROW HIERARCHY: rows -> OD legs -> trips")

n_trips = df["trip_uuid"].nunique()
od_key = ["trip_uuid", "source_center", "destination_center"]
n_legs = df[od_key].drop_duplicates().shape[0]
emit(f"\nB1. rows={len(df)}, distinct trip_uuid={n_trips}, "
     f"distinct (trip,source,dest) legs={n_legs}")

rows_per_trip = df.groupby("trip_uuid").size()
legs_per_trip = df[od_key].drop_duplicates().groupby("trip_uuid").size()
rows_per_leg = df.groupby(od_key).size()
emit("rows per trip:      " + rows_per_trip.describe().round(2).to_string().replace("\n", " | "))
emit("legs per trip:      " + legs_per_trip.describe().round(2).to_string().replace("\n", " | "))
emit("rows per leg:       " + rows_per_leg.describe().round(2).to_string().replace("\n", " | "))
emit("legs-per-trip value counts (top 12):")
emit("    " + legs_per_trip.value_counts().head(12).to_string().replace("\n", "\n    "))

emit("\nB2. constancy within trip / within leg:")
for col in ["route_type", "route_schedule_uuid", "trip_creation_time", "data"]:
    nun = df.groupby("trip_uuid")[col].nunique()
    emit(f"  trips where {col} varies within trip: {(nun > 1).sum()}")
for col in ["od_start_time", "od_end_time", "start_scan_to_end_scan"]:
    nun = df.groupby(od_key)[col].nunique(dropna=False)
    emit(f"  legs where {col} varies within leg: {(nun > 1).sum()}")

emit("\nB3. cumulative-vs-incremental test (the load-bearing structural fact):")
# Hypothesis: within a leg in file order, actual_time/osrm_time/osrm_distance
# are cumulative (non-decreasing) and segment_* are per-row increments whose
# sum reproduces the leg's final cumulative value.
g = df.groupby(od_key, sort=False)
mono = g["actual_time"].apply(lambda s: s.is_monotonic_increasing)
emit(f"  legs where actual_time is non-decreasing in file order: "
     f"{mono.sum()} of {len(mono)} ({mono.mean()*100:.2f}%)")
last_cum = g["actual_time"].last()
seg_sum = g["segment_actual_time"].sum()
gap = (last_cum - seg_sum)
emit("  (last actual_time - sum segment_actual_time) per leg: "
     + gap.describe(percentiles=[.01, .5, .99]).round(2).to_string().replace("\n", " | "))
emit(f"  legs where |gap| <= 2 min: {(gap.abs() <= 2).sum()} ({(gap.abs() <= 2).mean()*100:.2f}%)")
for cum_col, seg_col in [("osrm_time", "segment_osrm_time"),
                         ("osrm_distance", "segment_osrm_distance")]:
    gap2 = g[cum_col].last() - g[seg_col].sum()
    emit(f"  {cum_col} vs sum {seg_col}: |gap|<=2 in "
         f"{(gap2.abs() <= 2).mean()*100:.2f}% of legs; "
         f"median gap {gap2.median():.2f}")

emit("\nB4. first row of each leg: does cumulative == segment (i.e., starts fresh)?")
first = g.first()
same = (first["actual_time"] == first["segment_actual_time"])
emit(f"  legs where first-row actual_time == segment_actual_time: "
     f"{same.sum()} ({same.mean()*100:.2f}%)")

emit("\nB5. does the cumulative counter reset per LEG or run across the whole TRIP?")
# For multi-leg trips: compare first actual_time of leg N+1 vs last of leg N.
multi = legs_per_trip[legs_per_trip > 1].index
sub = df[df["trip_uuid"].isin(multi)]
leg_first_last = sub.groupby(od_key, sort=False)["actual_time"].agg(["first", "last"])
leg_first_last = leg_first_last.reset_index()
nxt = leg_first_last.groupby("trip_uuid", sort=False)
carry = 0
fresh = 0
for _, grp in nxt:
    for i in range(1, len(grp)):
        if grp["first"].iloc[i] >= grp["last"].iloc[i - 1]:
            carry += 1
        else:
            fresh += 1
emit(f"  leg transitions where next leg's first cumulative >= prev leg's last: {carry}")
emit(f"  leg transitions where it resets lower (fresh counter): {fresh}")

emit("\nB6. actual_distance_to_destination behavior within leg:")
dec = g["actual_distance_to_destination"].apply(lambda s: s.is_monotonic_decreasing)
inc = g["actual_distance_to_destination"].apply(lambda s: s.is_monotonic_increasing)
emit(f"  legs monotonic decreasing: {dec.sum()} ({dec.mean()*100:.1f}%), "
     f"monotonic increasing: {inc.sum()} ({inc.mean()*100:.1f}%) of {len(dec)}")

emit("\nB7. cutoff fields:")
emit(f"  is_cutoff value counts: "
     + df["is_cutoff"].value_counts(dropna=False).to_string().replace("\n", " | "))
emit("  cutoff_factor describe: "
     + df["cutoff_factor"].describe().round(2).to_string().replace("\n", " | "))
emit(f"  cutoff_timestamp nulls: {df['cutoff_timestamp'].isna().sum()}")

# ---------------------------------------------------------- C. graph yield
section("C. GRAPH YIELD: nodes, corridors, repeat density (Rule-11 units)")

src = set(df["source_center"])
dst = set(df["destination_center"])
emit(f"\nC1. distinct source centers: {len(src)}, destination centers: {len(dst)}, "
     f"union (graph nodes): {len(src | dst)}")
emit(f"  source-only nodes: {len(src - dst)}, destination-only nodes: {len(dst - src)}")

# corridor = directed (source_center, destination_center); one observation per LEG
legs = df[od_key].drop_duplicates()
corr = legs.groupby(["source_center", "destination_center"]).size()
emit(f"\nC2. distinct directed corridors: {len(corr)}")
emit("  legs (observations) per corridor: "
     + corr.describe(percentiles=[.25, .5, .75, .9, .99]).round(2).to_string().replace("\n", " | "))
for k in [1, 2, 5, 10, 20]:
    emit(f"  corridors with >= {k} leg observations: {(corr >= k).sum()} "
         f"({(corr >= k).mean()*100:.1f}%)  -> covering "
         f"{corr[corr >= k].sum()} legs ({corr[corr >= k].sum()/corr.sum()*100:.1f}% of legs)")

emit("\nC3. corridor repeat density BY ROUTE TYPE:")
legs_rt = df[od_key + ["route_type"]].drop_duplicates()
for rt, grp in legs_rt.groupby("route_type"):
    c = grp.groupby(["source_center", "destination_center"]).size()
    emit(f"  {rt}: legs={len(grp)}, corridors={len(c)}, "
         f"median obs/corridor={c.median():.0f}, >=5 obs: {(c >= 5).mean()*100:.1f}%")

emit("\nC4. center code <-> name consistency:")
s_names = df.groupby("source_center")["source_name"].nunique(dropna=False)
d_names = df.groupby("destination_center")["destination_name"].nunique(dropna=False)
emit(f"  source codes with >1 name: {(s_names > 1).sum()}; "
     f"destination codes with >1 name: {(d_names > 1).sum()}")
if (s_names > 1).any():
    ex = s_names[s_names > 1].index[:3]
    for code in ex:
        emit(f"    {code}: {df.loc[df['source_center'] == code, 'source_name'].dropna().unique()[:4]}")
emit(f"  source_name nulls: {df['source_name'].isna().sum()} rows, "
     f"destination_name nulls: {df['destination_name'].isna().sum()} rows")

emit("\nC5. state extraction from names (for geo aggregation):")
st = df["source_name"].dropna().str.extract(r"\(([^)]+)\)$")[0]
emit(f"  source rows with parseable (State) suffix: {st.notna().sum()} of {df['source_name'].notna().sum()}")
emit("  top 12 states: " + st.value_counts().head(12).to_string().replace("\n", " | "))

# --------------------------------------------------------- D. target audit
section("D. TARGET INTEGRITY: actual vs OSRM, factor fields")

emit("\nD1. leg-level (last cumulative row per leg) actual_time vs osrm_time:")
leg_last = g.last()
emit("  actual_time:  " + leg_last["actual_time"].describe(
    percentiles=[.01, .25, .5, .75, .99]).round(1).to_string().replace("\n", " | "))
emit("  osrm_time:    " + leg_last["osrm_time"].describe(
    percentiles=[.01, .25, .5, .75, .99]).round(1).to_string().replace("\n", " | "))
emit(f"  legs with osrm_time <= 0: {(leg_last['osrm_time'] <= 0).sum()}, "
     f"actual_time <= 0: {(leg_last['actual_time'] <= 0).sum()}, "
     f"nulls: osrm={leg_last['osrm_time'].isna().sum()}, actual={leg_last['actual_time'].isna().sum()}")
ratio = leg_last["actual_time"] / leg_last["osrm_time"]
emit("  delay ratio actual/osrm per leg: "
     + ratio.describe(percentiles=[.05, .25, .5, .75, .95, .99]).round(3).to_string().replace("\n", " | "))
emit(f"  legs with actual > osrm: {(ratio > 1).mean()*100:.1f}%; "
     f"> 1.2 (brief's chronic threshold): {(ratio > 1.2).mean()*100:.1f}%; "
     f"underestimate by >2x: {(ratio > 2).mean()*100:.1f}%")

emit("\nD2. is 'factor' == actual_time/osrm_time row-wise?")
chk = (df["factor"] - df["actual_time"] / df["osrm_time"]).abs()
emit(f"  rows where |factor - actual/osrm| < 0.01: {(chk < 0.01).mean()*100:.2f}% "
     f"(nulls/inf excluded: {chk.isna().sum()})")
chk2 = (df["segment_factor"] - df["segment_actual_time"] / df["segment_osrm_time"]).abs()
emit(f"  rows where |segment_factor - seg_actual/seg_osrm| < 0.01: {(chk2 < 0.01).mean()*100:.2f}% "
     f"(nan: {chk2.isna().sum()})")

emit("\nD3. start_scan_to_end_scan vs od_end - od_start:")
ods = pd.to_datetime(df["od_start_time"], errors="coerce")
ode = pd.to_datetime(df["od_end_time"], errors="coerce")
od_min = (ode - ods).dt.total_seconds() / 60
diff = df["start_scan_to_end_scan"] - od_min
emit("  (start_scan_to_end_scan - od duration in min): "
     + diff.describe(percentiles=[.01, .5, .99]).round(2).to_string().replace("\n", " | "))
emit(f"  od_end < od_start rows: {(ode < ods).sum()}; unparseable timestamps: "
     f"start={ods.isna().sum()}, end={ode.isna().sum()}")

emit("\nD4. leg duration vs leg-level cumulative actual_time:")
leg_dur = df.assign(_dur=od_min).groupby(od_key)["_dur"].first()
dgap = leg_dur - leg_last["actual_time"]
emit("  (od duration - last actual_time) per leg: "
     + dgap.describe(percentiles=[.01, .5, .99]).round(1).to_string().replace("\n", " | "))

emit("\nD5. segment-level zero/negative anomalies:")
for c in ["segment_actual_time", "segment_osrm_time", "segment_osrm_distance",
          "actual_time", "osrm_time", "osrm_distance"]:
    emit(f"  {c}: negatives={int((df[c] < 0).sum())}, zeros={int((df[c] == 0).sum())}, "
         f"nulls={int(df[c].isna().sum())}")

# ------------------------------------------------------------- E. time/split
section("E. TIME COVERAGE / ROUTE TYPE / TRAIN-TEST SPLIT")

tct = pd.to_datetime(df["trip_creation_time"], errors="coerce")
emit(f"\nE1. trip_creation_time range: {tct.min()} .. {tct.max()} "
     f"(unparseable: {tct.isna().sum()})")
trips = df.drop_duplicates("trip_uuid")
ttct = pd.to_datetime(trips["trip_creation_time"], errors="coerce")
emit("  trips per calendar day (describe): "
     + ttct.dt.date.value_counts().describe().round(1).to_string().replace("\n", " | "))
emit("  trips by hour of day:")
emit("    " + ttct.dt.hour.value_counts().sort_index().to_string().replace("\n", "\n    "))

emit("\nE2. route_type at TRIP level:")
emit("    " + trips["route_type"].value_counts(dropna=False).to_string().replace("\n", "\n    "))

emit("\nE3. data (train/test) split:")
emit(f"  rows:  " + df["data"].value_counts().to_string().replace("\n", " | "))
emit(f"  trips: " + trips["data"].value_counts().to_string().replace("\n", " | "))
tr_trips = set(df.loc[df["data"] == "training", "trip_uuid"])
te_trips = set(df.loc[df["data"] != "training", "trip_uuid"])
emit(f"  trips appearing in BOTH splits: {len(tr_trips & te_trips)}")
tr_t = ttct[trips["data"] == "training"]
te_t = ttct[trips["data"] != "training"]
emit(f"  training trip dates: {tr_t.min()} .. {tr_t.max()}")
emit(f"  test     trip dates: {te_t.min()} .. {te_t.max()}  "
     f"(temporal split? overlap matters for leakage)")
tr_corr = set(map(tuple, df.loc[df['data'] == 'training', ['source_center', 'destination_center']].drop_duplicates().values))
te_corr = set(map(tuple, df.loc[df['data'] != 'training', ['source_center', 'destination_center']].drop_duplicates().values))
emit(f"  test corridors never seen in training: {len(te_corr - tr_corr)} of {len(te_corr)} "
     f"({len(te_corr - tr_corr)/max(len(te_corr),1)*100:.1f}%)  [cold-start exposure]")

# ------------------------------------------------- F. follow-up verification
section("F. FOLLOW-UP CHECKS (verify inferences from A-E)")

emit("\nF1. the 21 negative segment_actual_time rows:")
neg = df[df["segment_actual_time"] < 0]
emit(neg[["trip_uuid", "source_center", "destination_center", "actual_time",
          "segment_actual_time", "segment_osrm_time"]].head(10).to_string())
emit(f"  distinct legs affected: {neg.groupby(od_key).ngroups}")

emit("\nF2. cutoff_factor semantics — is it the cumulative actual_time at the cutoff row?")
chk_cut = (df["cutoff_factor"] - df["actual_time"]).abs()
emit(f"  rows where |cutoff_factor - actual_time| < 1: {(chk_cut < 1).mean()*100:.2f}%")
emit(f"  rows where cutoff_factor == round(actual_time): "
     f"{(df['cutoff_factor'] == df['actual_time'].round()).mean()*100:.2f}%")
emit("  by is_cutoff:")
for v, grp in df.groupby("is_cutoff"):
    m = (grp["cutoff_factor"] - grp["actual_time"]).abs() < 1
    emit(f"    is_cutoff={v}: n={len(grp)}, |cutoff_factor-actual_time|<1 in {m.mean()*100:.2f}%")

emit("\nF3. actual_distance_to_destination: cumulative distance traveled, not remaining?")
# If cumulative-traveled, the leg's LAST value should track osrm_distance scale.
leg_last_dist = g["actual_distance_to_destination"].last()
ratio_d = leg_last_dist / leg_last["osrm_distance"]
emit("  last actual_distance_to_destination / last osrm_distance per leg: "
     + ratio_d.describe(percentiles=[.05, .5, .95]).round(3).to_string().replace("\n", " | "))
first_dist = g["actual_distance_to_destination"].first()
emit("  first-row value describe: "
     + first_dist.describe(percentiles=[.5, .95]).round(1).to_string().replace("\n", " | "))

emit("\nF4. the 1 leg where od_start/od_end varies within leg:")
vleg = df.groupby(od_key)["od_start_time"].nunique()
vkey = vleg[vleg > 1].index
for k in vkey:
    rows = df[(df["trip_uuid"] == k[0]) & (df["source_center"] == k[1])
              & (df["destination_center"] == k[2])]
    emit(rows[["trip_uuid", "source_center", "destination_center", "od_start_time",
               "od_end_time", "actual_time", "segment_actual_time"]].to_string())

emit("\nF5. trips revisiting the same OD pair (leg key collisions across a trip)?")
# If a trip visits A->B twice, our leg key merges two physical legs. Detect via
# non-monotonic actual_time legs (B3 found 21).
nonmono = mono[~mono].index
emit(f"  legs with non-monotonic actual_time: {len(nonmono)} (same 21 expected from B3)")
if len(nonmono):
    k = nonmono[0]
    rows = df[(df["trip_uuid"] == k[0]) & (df["source_center"] == k[1])
              & (df["destination_center"] == k[2])]
    emit(rows[["trip_uuid", "source_center", "destination_center", "actual_time",
               "segment_actual_time", "od_start_time"]].head(12).to_string())

emit("\nF6. hub concentration — share of legs touching top-20 centers (graph skew):")
touch = pd.concat([legs["source_center"], legs["destination_center"]])
top20 = touch.value_counts().head(20)
emit("    " + top20.to_string().replace("\n", "\n    "))
emit(f"  top-20 centers account for {top20.sum()/(2*len(legs))*100:.1f}% of leg endpoints")

# ----------------------------------------------------------------- save
report = os.path.join(PROJ, "probe-report.txt")
with open(report, "w", encoding="utf-8") as f:
    f.write(buf.getvalue())
print(f"\n[saved] {report}")
