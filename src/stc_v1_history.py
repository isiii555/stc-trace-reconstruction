import pandas as pd
from pathlib import Path
from datetime import timedelta
from collections import deque

IN_PATH = Path("out/eventlog_oracle_blockid.csv")
OUT_PATH = Path("out/eventlog_STC_v1_history.csv")

# ---- Hyperparameters (report in thesis) ----
DELTA_SECONDS = 5          # try 2, 5, 10 (you already tested those)
K_HISTORY = 5              # last-K activities remembered per trace
MAX_OPEN_TRACES = 5000     # keep bounded
HIT_IN_HISTORY_BONUS = 2.0
SAME_COMPONENT_BONUS = 1.0

df = pd.read_csv(IN_PATH)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

events = df.to_dict("records")

open_traces = {}   # trace_id -> dict(last_ts, component, history(deque))
trace_ids = []
next_trace_id = 1
delta = timedelta(seconds=DELTA_SECONDS)

def score(ev, tr):
    s = 0.0
    # history match
    if ev["activity"] in tr["history"]:
        s += HIT_IN_HISTORY_BONUS
    # component match
    if ev["component"] == tr["component"]:
        s += SAME_COMPONENT_BONUS
    return s

for ev in events:
    ts = ev["timestamp"]

    # close inactive traces
    to_close = [tid for tid, tr in open_traces.items() if ts - tr["last_ts"] > delta]
    for tid in to_close:
        del open_traces[tid]

    # choose best trace
    best_tid = None
    best_score = -1.0
    for tid, tr in open_traces.items():
        s = score(ev, tr)
        if s > best_score:
            best_score = s
            best_tid = tid

    # assign
    if best_tid is None or best_score <= 0.0:
        tid = f"stc_{next_trace_id}"
        next_trace_id += 1
        open_traces[tid] = {
            "last_ts": ts,
            "component": ev["component"],
            "history": deque([ev["activity"]], maxlen=K_HISTORY),
        }
    else:
        tid = best_tid
        tr = open_traces[tid]
        tr["last_ts"] = ts
        tr["component"] = ev["component"]  # update to most recent component
        tr["history"].append(ev["activity"])

    trace_ids.append(tid)

    # bound open traces
    if len(open_traces) > MAX_OPEN_TRACES:
        # drop oldest
        oldest = sorted(open_traces.items(), key=lambda x: x[1]["last_ts"])[: len(open_traces) - MAX_OPEN_TRACES]
        for tid_old, _ in oldest:
            del open_traces[tid_old]

df_out = df.copy()
df_out["case_id"] = trace_ids
df_out.to_csv(OUT_PATH, index=False)

print("Saved:", OUT_PATH)
print("Events:", len(df_out))
print("Cases (STC v1):", df_out["case_id"].nunique())
print("Params: DELTA_SECONDS =", DELTA_SECONDS, ", K_HISTORY =", K_HISTORY)
