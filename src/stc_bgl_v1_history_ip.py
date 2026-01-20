import pandas as pd
from pathlib import Path
from datetime import timedelta
from collections import deque

# ----------------------------
# STC for BGL (correlation-weak)
# Input: BGL event log CSV with timestamp/component/node_id/activity
# Output: reconstructed traces (case_id = stc_*)
# ----------------------------

# ---- Hyperparameters (MT3) ----
DELTA_SECONDS = 5
K_HISTORY = 5
MAX_OPEN_TRACES = 5000

# Use node-based baseline as input stream (already structured)
IN_PATH = Path("out_bgl/eventlog_B2_node_timegap_5s.csv")
OUT_PATH = Path(f"out_bgl/eventlog_STC_bgl_delta{DELTA_SECONDS}s.csv")

HIT_IN_HISTORY_BONUS = 2.0
SAME_COMPONENT_BONUS = 1.0
SAME_NODE_BONUS = 2.0
SAME_LEVEL_BONUS = 0.5

df = pd.read_csv(IN_PATH)

df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

events = df.to_dict("records")
delta = timedelta(seconds=DELTA_SECONDS)

open_traces = {}   # trace_id -> state
trace_ids = []
next_trace_id = 1

def score(ev, tr):
    s = 0.0
    if ev["activity"] in tr["history"]:
        s += HIT_IN_HISTORY_BONUS
    if ev.get("component","") == tr.get("component",""):
        s += SAME_COMPONENT_BONUS
    if ev.get("node_id","") and ev.get("node_id","") == tr.get("node_id",""):
        s += SAME_NODE_BONUS
    if ev.get("level","") and ev.get("level","") == tr.get("level",""):
        s += SAME_LEVEL_BONUS
    return s

for ev in events:
    ts = ev["timestamp"]

    # close inactive traces
    to_close = [tid for tid, tr in open_traces.items() if ts - tr["last_ts"] > delta]
    for tid in to_close:
        del open_traces[tid]

    # best match
    best_tid = None
    best_score = -1.0
    for tid, tr in open_traces.items():
        sc = score(ev, tr)
        if sc > best_score:
            best_score = sc
            best_tid = tid

    # assign
    if best_tid is None or best_score <= 0.0:
        tid = f"stc_{next_trace_id}"
        next_trace_id += 1
        open_traces[tid] = {
            "last_ts": ts,
            "component": ev.get("component",""),
            "node_id": ev.get("node_id",""),
            "level": ev.get("level",""),
            "history": deque([ev["activity"]], maxlen=K_HISTORY),
        }
    else:
        tid = best_tid
        tr = open_traces[tid]
        tr["last_ts"] = ts
        tr["component"] = ev.get("component","")
        tr["node_id"] = ev.get("node_id","")
        tr["level"] = ev.get("level","")
        tr["history"].append(ev["activity"])

    trace_ids.append(tid)

    # bound open traces
    if len(open_traces) > MAX_OPEN_TRACES:
        oldest = sorted(open_traces.items(), key=lambda x: x[1]["last_ts"])[: len(open_traces) - MAX_OPEN_TRACES]
        for tid_old, _ in oldest:
            del open_traces[tid_old]

df_out = df.copy()
df_out["case_id"] = trace_ids
df_out.to_csv(OUT_PATH, index=False)

print("Saved:", OUT_PATH)
print("Events:", len(df_out))
print("Cases (STC BGL):", df_out["case_id"].nunique())
print("Params: DELTA_SECONDS =", DELTA_SECONDS, ", K_HISTORY =", K_HISTORY)
