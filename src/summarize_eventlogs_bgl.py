import pandas as pd
from pathlib import Path

FILES = [
    ("B3 single trace", Path("out_bgl/eventlog_B3_single_trace.csv")),
    ("B2 global timegap 60s", Path("out_bgl/eventlog_B2_timegap_60s.csv")),
    ("B2' node timegap 5s", Path("out_bgl/eventlog_B2_node_timegap_5s.csv")),
    ("STC BGL delta=5s", Path("out_bgl/eventlog_STC_bgl_delta5s.csv")),
]

def summarize(path: Path):
    df = pd.read_csv(path, low_memory=False)
    if "case_id" not in df.columns:
        raise ValueError(f"{path} is missing 'case_id' column. Columns: {list(df.columns)}")

    df["case_id"] = df["case_id"].astype(str)

    n_events = len(df)
    n_cases = df["case_id"].nunique()
    sizes = df.groupby("case_id").size()

    single_pct = 100.0 * (sizes == 1).mean()

    return {
        "events": n_events,
        "cases": n_cases,
        "avg_trace_len": float(sizes.mean()),
        "median_trace_len": float(sizes.median()),
        "max_trace_len": int(sizes.max()),
        "single_event_pct": round(single_pct, 2),
    }

rows = []
for name, p in FILES:
    s = summarize(p)
    s["method"] = name
    rows.append(s)

out = pd.DataFrame(rows)[
    ["method","events","cases","avg_trace_len","median_trace_len","max_trace_len","single_event_pct"]
]
print(out.to_string(index=False))

out_path = Path("out_bgl/summary_table_bgl.csv")
out.to_csv(out_path, index=False)
print(f"\nSaved: {out_path}")
