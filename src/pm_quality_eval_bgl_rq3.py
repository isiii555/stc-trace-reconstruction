import pandas as pd
from pathlib import Path
import pm4py
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.util import dataframe_utils

# BGL logs to compare (baselines + STC)
LOGS = [
    ("B3 single trace", Path("out_bgl/eventlog_B3_single_trace.csv")),
    ("B2 global timegap 60s", Path("out_bgl/eventlog_B2_timegap_60s.csv")),
    ("B2' node timegap 5s", Path("out_bgl/eventlog_B2_node_timegap_5s.csv")),
    ("STC BGL delta=5s", Path("out_bgl/eventlog_STC_bgl_delta5s.csv")),
]

CASE_COL = "case_id"
ACT_COL  = "activity"
TIME_COL = "timestamp"

# MT3-friendly sampling (same style as HDFS RQ2 evaluation)
MAX_EVENTS_PER_CASE = 10
MAX_TOTAL_EVENTS = 2000  # BGL_2k is already small; keep =2000

def load_csv_as_eventlog(path: Path):
    df = pd.read_csv(path)
    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce")
    df = df.dropna(subset=[TIME_COL, CASE_COL, ACT_COL])

    df = df.rename(columns={
        CASE_COL: "case:concept:name",
        ACT_COL:  "concept:name",
        TIME_COL: "time:timestamp"
    })

    df = df.sort_values(["case:concept:name", "time:timestamp"]).reset_index(drop=True)

    if MAX_EVENTS_PER_CASE and MAX_EVENTS_PER_CASE > 0:
        df = df.groupby("case:concept:name").head(MAX_EVENTS_PER_CASE).reset_index(drop=True)

    if MAX_TOTAL_EVENTS and MAX_TOTAL_EVENTS > 0 and len(df) > MAX_TOTAL_EVENTS:
        df = df.head(MAX_TOTAL_EVENTS).reset_index(drop=True)

    cases_used = df["case:concept:name"].nunique()
    events_used = len(df)

    df = dataframe_utils.convert_timestamp_columns_in_df(df)
    log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
    return log, cases_used, events_used

def eval_one(name, path):
    print(f"\nEvaluating: {name}")
    log, cases_used, events_used = load_csv_as_eventlog(path)
    print(f"  cases={cases_used}, events={events_used}")

    net, im, fm = pm4py.discover_petri_net_inductive(log)

    # token-based replay (works on your pm4py version)
    fitness = pm4py.fitness_token_based_replay(log, net, im, fm)["log_fitness"]
    precision = pm4py.precision_token_based_replay(log, net, im, fm)

    return {
        "method": name,
        "cases_used": int(cases_used),
        "events_used": int(events_used),
        "fitness": round(float(fitness), 4),
        "precision": round(float(precision), 4),
        "cap_per_case": MAX_EVENTS_PER_CASE,
        "cap_total_events": MAX_TOTAL_EVENTS,
    }

rows = []
for name, path in LOGS:
    rows.append(eval_one(name, path))

out = pd.DataFrame(rows)[["method","cases_used","events_used","fitness","precision","cap_per_case","cap_total_events"]]
print("\n=== BGL Downstream PM Results (Inductive Miner) ===")
print(out.to_string(index=False))

out_path = Path("out_bgl/pm_quality_table_bgl.csv")
out.to_csv(out_path, index=False)
print(f"\nSaved: {out_path}")
