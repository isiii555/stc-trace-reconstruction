import pandas as pd
from pathlib import Path
from datetime import timedelta

IN_PATH = Path("out/eventlog_oracle_blockid.csv")   # contains timestamp/template/component/level/block_id
OUT_PATH = Path("out/eventlog_STC_v0.csv")

# --- Hyperparameters (report these in thesis) ---
DELTA_SECONDS = 10          # max time gap to attach to an open trace
MAX_OPEN_TRACES = 2000     # cap for memory; oldest traces are closed
SAME_TEMPLATE_BONUS = 2.0
SAME_COMPONENT_BONUS = 1.0

df = pd.read_csv(IN_PATH)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

# Simulate "missing correlation": we DO NOT use block_id to group cases.
# We will construct new case_id.
events = df.to_dict("records")

open_traces = {}   # trace_id -> dict(last_ts, last_activity, component)
trace_events = []  # list of assigned trace_id per event row

next_trace_id = 1

def score_event_to_trace(ev, tr):
    score = 0.0
    if ev["activity"] == tr["last_activity"]:
        score += SAME_TEMPLATE_BONUS
    if ev["component"] == tr["component"]:
        score += SAME_COMPONENT_BONUS
    return score

for ev in events:
    ts = ev["timestamp"]

    # 1) Close traces that are too old (inactive)
    to_close = []
    for tid, tr in open_traces.items():
        if ts - tr["last_ts"] > timedelta(seconds=DELTA_SECONDS):
            to_close.append(tid)
    for tid in to_close:
        del open_traces[tid]

    # 2) Find best matching open trace
    best_tid = None
    best_score = -1.0

    for tid, tr in open_traces.items():
        # time constraint already ensured by closing old traces
        s = score_event_to_trace(ev, tr)
        if s > best_score:
            best_score = s
            best_tid = tid

    # 3) Assign: if no good match, start a new trace
    # Require at least some weak match OR no open traces
    if best_tid is None or best_score <= 0.0:
        tid = f"stc_{next_trace_id}"
        next_trace_id += 1
    else:
        tid = best_tid

    trace_events.append(tid)

    # 4) Update / open trace state
    open_traces[tid] = {
        "last_ts": ts,
        "last_activity": ev["activity"],
        "component": ev["component"],
    }

    # 5) Keep open trace set bounded (avoid growth if logs are dense)
    if len(open_traces) > MAX_OPEN_TRACES:
        # remove the oldest traces
        oldest = sorted(open_traces.items(), key=lambda x: x[1]["last_ts"])[: len(open_traces) - MAX_OPEN_TRACES]
        for tid_old, _ in oldest:
            del open_traces[tid_old]

df_out = df.copy()
df_out["case_id"] = trace_events
df_out.to_csv(OUT_PATH, index=False)

print("Saved:", OUT_PATH)
print("Events:", len(df_out))
print("Cases (STC v0):", df_out["case_id"].nunique())
