import pandas as pd
from pathlib import Path

IN_PATH = Path("out/eventlog_oracle_blockid.csv")
OUT_PATH = Path("out/eventlog_B2_component_timegap_5s.csv")

GAP_SECONDS = 5

df = pd.read_csv(IN_PATH)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp"])

# simulate missing correlation attribute
# we do NOT use block_id
df = df.sort_values(["component", "timestamp"]).copy()

case_id_series = pd.Series(index=df.index, dtype="object")

for comp, g in df.groupby("component", sort=False):
    g = g.sort_values("timestamp")
    local_case = 0
    prev = None
    for idx, ts in zip(g.index, g["timestamp"]):
        if prev is None or (ts - prev).total_seconds() > GAP_SECONDS:
            local_case += 1
        case_id_series.loc[idx] = f"{comp}_c{local_case}"
        prev = ts

df["case_id"] = case_id_series
df.to_csv(OUT_PATH, index=False)

print("Saved:", OUT_PATH)
print("Cases:", df["case_id"].nunique(), "Events:", len(df))
