import pandas as pd
from pathlib import Path

ORACLE = Path("out/eventlog_oracle_blockid.csv")
STC = Path("out/eventlog_STC_v2_history_ip.csv")

df_o = pd.read_csv(ORACLE, usecols=["timestamp", "activity", "component", "level", "block_id"])
df_s = pd.read_csv(STC, usecols=["timestamp", "activity", "component", "level", "case_id"])

# Align rows by order (same events exported in same order)
if len(df_o) != len(df_s):
    raise ValueError("Row counts differ; ensure STC was built from the same oracle file.")

df = df_s.copy()
df["block_id"] = df_o["block_id"].astype(str)

# Purity per constructed trace
purities = []
for case_id, g in df.groupby("case_id"):
    counts = g["block_id"].value_counts()
    purity = counts.iloc[0] / len(g)
    purities.append(purity)

print("Constructed traces:", df["case_id"].nunique())
print("Avg purity:", sum(purities) / len(purities))
print("Median purity:", sorted(purities)[len(purities)//2])
