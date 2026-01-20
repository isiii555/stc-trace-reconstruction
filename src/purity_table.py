import pandas as pd
from pathlib import Path

ORACLE = Path("out/eventlog_oracle_blockid.csv")

STC_FILES = [
    ("STC v2 delta=2s", Path("out/eventlog_STC_v2_history_ip_delta2s.csv")),
    ("STC v2 delta=5s", Path("out/eventlog_STC_v2_history_ip_delta5s.csv")),
    ("STC v2 delta=10s", Path("out/eventlog_STC_v2_history_ip_delta10s.csv")),
]

df_o = pd.read_csv(ORACLE, usecols=["block_id"])
df_o["block_id"] = df_o["block_id"].astype(str)

rows = []

for name, path in STC_FILES:
    df_s = pd.read_csv(path, usecols=["case_id"])
    if len(df_s) != len(df_o):
        raise ValueError(f"Row mismatch for {path}: {len(df_s)} vs {len(df_o)}")

    df = df_s.copy()
    df["block_id"] = df_o["block_id"]

    purities = []
    for _, g in df.groupby("case_id"):
        vc = g["block_id"].value_counts()
        purities.append(vc.iloc[0] / len(g))

    purities_sorted = sorted(purities)
    avg_purity = sum(purities) / len(purities)
    med_purity = purities_sorted[len(purities_sorted) // 2]

    # NEW metrics
    mixed_pct = 100.0 * sum(p < 1.0 for p in purities) / len(purities)
    p90 = purities_sorted[int(0.9 * (len(purities_sorted) - 1))]

    rows.append({
        "method": name,
        "cases": len(purities),
        "avg_purity": round(avg_purity, 4),
        "median_purity": round(med_purity, 4),
        "p90_purity": round(p90, 4),
        "mixed_trace_pct": round(mixed_pct, 2),
    })

out = pd.DataFrame(rows)[["method", "cases", "avg_purity", "median_purity", "p90_purity", "mixed_trace_pct"]]
print(out.to_string(index=False))
out.to_csv("out/purity_table.csv", index=False)
print("\nSaved: out/purity_table.csv")
