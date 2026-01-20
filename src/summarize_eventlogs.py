import pandas as pd
from pathlib import Path

files = [
    ("Oracle (block_id)", Path("out/eventlog_oracle_blockid.csv")),
    ("B3 Single trace", Path("out/eventlog_B3_single_trace.csv")),
    ("B2 Global timegap 60s", Path("out/eventlog_B2_timegap_60s.csv")),  # optional
    ("B2 Component timegap 5s", Path("out/eventlog_B2_component_timegap_5s.csv")),
    ("STC v2 (history+IP, Δ=2s)", Path("out/eventlog_STC_v2_history_ip_delta2s.csv")),
    ("STC v2 (history+IP, Δ=5s)", Path("out/eventlog_STC_v2_history_ip_delta5s.csv")),
    ("STC v2 (history+IP, Δ=10s)", Path("out/eventlog_STC_v2_history_ip_delta10s.csv")),
]

def summarize(path: Path):
    if not path.exists():
        return None  # skip missing files safely

    df = pd.read_csv(path, low_memory=False)
    n_events = len(df)
    n_cases = df["case_id"].nunique()
    sizes = df.groupby("case_id").size()

    return {
        "events": n_events,
        "cases": n_cases,
        "avg_trace_len": float(sizes.mean()),
        "median_trace_len": float(sizes.median()),
        "max_trace_len": int(sizes.max()),
    }

rows = []
skipped = []
for name, p in files:
    s = summarize(p)
    if s is None:
        skipped.append(str(p))
        continue
    s["method"] = name
    rows.append(s)

out = pd.DataFrame(rows)[["method", "events", "cases", "avg_trace_len", "median_trace_len", "max_trace_len"]]
print(out.to_string(index=False))
out.to_csv("out/summary_table.csv", index=False)
