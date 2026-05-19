from pathlib import Path
import pandas as pd

path = Path("out/eventlog_oracle_blockid.csv")

df = pd.read_csv(path)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

gaps = df["timestamp"].diff().dt.total_seconds().fillna(0)

print("Events:", len(df))
print("Min gap:", gaps.min())
print("Max gap:", gaps.max())
print("Mean gap:", gaps.mean())
print("Median gap:", gaps.median())
print("Gaps > 1 sec:", (gaps > 1).sum())
print("Gaps > 2 sec:", (gaps > 2).sum())
print("Gaps > 5 sec:", (gaps > 5).sum())
print("Gaps > 10 sec:", (gaps > 10).sum())
print("Gaps > 30 sec:", (gaps > 30).sum())
print("Gaps > 60 sec:", (gaps > 60).sum())