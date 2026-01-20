import pandas as pd
from pathlib import Path

ORACLE = Path("out/eventlog_oracle_blockid.csv")

METHOD_FILES = [
    ("Baseline B3: single trace", Path("out/eventlog_B3_single_trace.csv")),
    ("Baseline B2: global timegap 60s", Path("out/eventlog_B2_timegap_60s.csv")),
    ("Baseline B2': component timegap 5s", Path("out/eventlog_B2_component_timegap_5s.csv")),
    ("STC delta=2s", Path("out/eventlog_STC_v2_history_ip_delta2s.csv")),
    ("STC delta=5s", Path("out/eventlog_STC_v2_history_ip_delta5s.csv")),
    ("STC delta=10s", Path("out/eventlog_STC_v2_history_ip_delta10s.csv")),
]

# Oracle block_id (reference grouping)
df_o = pd.read_csv(ORACLE, usecols=["block_id"])
df_o["block_id"] = df_o["block_id"].astype(str)

rows = []

for name, path in METHOD_FILES:
    df_m = pd.read_csv(path, usecols=["case_id"])
    if len(df_m) != len(df_o):
        raise ValueError(f"Row mismatch for {path}: {len(df_m)} vs {len(df_o)}")

    df = df_m.copy()
    df["block_id"] = df_o["block_id"]

    purities = []
    for _, g in df.groupby("case_id"):
        vc = g["block_id"].value_counts()
        purities.append(vc.iloc[0] / len(g))

    purities_sorted = sorted(purities)
    avg_purity = sum(purities) / len(purities)
    med_purity = purities_sorted[len(purities_sorted) // 2]
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
out.to_csv("out/purity_table_with_baselines.csv", index=False)
print("\nSaved: out/purity_table_with_baselines.csv")
