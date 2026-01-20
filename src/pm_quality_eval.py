import pandas as pd
from pathlib import Path

import pm4py
from pm4py.objects.conversion.log import converter as log_converter
from pm4py.objects.log.util import dataframe_utils

# -----------------------------
# RQ2 Downstream Process Mining Evaluation (MT3-friendly)
# - Inductive Miner discovery (Petri net)
# - Token-based fitness + precision (fast)
# - Case-balanced sampling + total event cap
# -----------------------------

LOGS = [
    ("Oracle (block_id)", Path("out/eventlog_oracle_blockid.csv")),
    ("Baseline B2' component timegap 5s", Path("out/eventlog_B2_component_timegap_5s.csv")),
    ("STC delta=5s", Path("out/eventlog_STC_v2_history_ip_delta5s.csv")),
]

# Input CSV columns in your exported logs
CASE_COL = "case_id"
ACT_COL  = "activity"
TIME_COL = "timestamp"

# ---- Sampling settings (change if needed) ----
MAX_EVENTS_PER_CASE = 10   # keep first N events per case (fast)
MAX_TOTAL_EVENTS    = 5000 # hard cap on total events after sampling (fast + safe)

# Token-based evaluation is fast and sufficient for MT3 demonstration of RQ2
USE_ALIGNMENT_BASED = False


def load_csv_as_eventlog(path: Path):
    """
    Load CSV as PM4Py event log.
    Applies:
      1) per-case cap (case-balanced)
      2) total event cap (safety)
    """
    df = pd.read_csv(path)

    # Parse time, drop incomplete rows
    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce")
    df = df.dropna(subset=[TIME_COL, CASE_COL, ACT_COL])

    # Rename to PM4Py standard columns
    df = df.rename(columns={
        CASE_COL: "case:concept:name",
        ACT_COL:  "concept:name",
        TIME_COL: "time:timestamp"
    })

    # Sort within cases
    df = df.sort_values(["case:concept:name", "time:timestamp"]).reset_index(drop=True)

    # Case-balanced sampling: cap events per case
    if MAX_EVENTS_PER_CASE and MAX_EVENTS_PER_CASE > 0:
        df = df.groupby("case:concept:name").head(MAX_EVENTS_PER_CASE).reset_index(drop=True)

    # Total cap to keep discovery/evaluation fast
    if MAX_TOTAL_EVENTS and MAX_TOTAL_EVENTS > 0 and len(df) > MAX_TOTAL_EVENTS:
        df = df.head(MAX_TOTAL_EVENTS).reset_index(drop=True)

    cases_used = df["case:concept:name"].nunique()
    events_used = len(df)

    # PM4Py timestamp conversion helper
    df = dataframe_utils.convert_timestamp_columns_in_df(df)

    # Convert to event log
    log = log_converter.apply(df, variant=log_converter.Variants.TO_EVENT_LOG)
    return log, cases_used, events_used


def evaluate_one(name: str, path: Path):
    print(f"\nEvaluating: {name}")
    print(f"  Reading: {path}")

    log, cases_used, events_used = load_csv_as_eventlog(path)
    print(f"  Loaded subset: cases={cases_used}, events={events_used}")
    print("  Discovering model (Inductive Miner)...")

    # Petri net from Inductive Miner (stable wrapper)
    net, im, fm = pm4py.discover_petri_net_inductive(log)

    print("  Computing fitness/precision...")

    if USE_ALIGNMENT_BASED:
        # Slower, not recommended for MT3 on large logs
        fitness = pm4py.fitness_alignments(log, net, im, fm)["log_fitness"]
        precision = pm4py.precision_alignments(log, net, im, fm)
        eval_type = "alignment"
    else:
        # Fast and stable
        fitness = pm4py.fitness_token_based_replay(log, net, im, fm)["log_fitness"]
        precision = pm4py.precision_token_based_replay(log, net, im, fm)
        eval_type = "token"

    print("  Done.")

    return {
        "method": name,
        "cases_used": int(cases_used),
        "events_used": int(events_used),
        "fitness": round(float(fitness), 4),
        "precision": round(float(precision), 4),
        "eval_type": eval_type,
        "cap_per_case": int(MAX_EVENTS_PER_CASE),
        "cap_total_events": int(MAX_TOTAL_EVENTS),
    }


def main():
    rows = []
    for name, path in LOGS:
        rows.append(evaluate_one(name, path))

    out = pd.DataFrame(rows)[
        ["method", "cases_used", "events_used", "fitness", "precision",
         "eval_type", "cap_per_case", "cap_total_events"]
    ]

    print("\n=== RQ2 Downstream Process Mining Results (Inductive Miner) ===")
    print(out.to_string(index=False))

    out_path = Path("out/pm_quality_table_inductive_rq2.csv")
    out.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path}")

    print("\nReport this in thesis as:")
    print(f"- Inductive Miner on a case-balanced subset (cap {MAX_EVENTS_PER_CASE} events/case, max {MAX_TOTAL_EVENTS} events total)")
    print(f"- Token-based fitness/precision (fast MT3 evaluation)")


if __name__ == "__main__":
    main()
