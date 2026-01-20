import re
import csv
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

# Example BGL line (yours):
# - 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected
# APPREAD 1117869872 2005.06.04 R04-M1-N4-I:J18-U11 2005-06-04-00.24.32.432192 R04-M1-N4-I:J18-U11 RAS APP FATAL ciod: failed to read ...

TS2_RE = re.compile(r"\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}(?:\.\d+)?")

LEVELS = {"INFO","WARN","WARNING","ERROR","FATAL","DEBUG"}

HEX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
IP_RE  = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
NUM_RE = re.compile(r"\b\d+\b")

def parse_ts2(ts2: str) -> datetime | None:
    # 2005-06-03-15.42.50.675872  OR  2005-06-03-15.42.50
    for fmt in ("%Y-%m-%d-%H.%M.%S.%f", "%Y-%m-%d-%H.%M.%S"):
        try:
            return datetime.strptime(ts2, fmt)
        except ValueError:
            continue
    return None

def make_template(msg: str) -> str:
    s = msg
    s = HEX_RE.sub("<HEX>", s)
    s = IP_RE.sub("<IP>", s)
    s = NUM_RE.sub("<NUM>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:180]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to BGL log (e.g., data/BGL/BGL_2k.log)")
    ap.add_argument("--outdir", default="out_bgl", help="Output folder for BGL event logs")
    ap.add_argument("--gap_seconds", type=int, default=60, help="Global time-gap baseline B2")
    ap.add_argument("--node_gap_seconds", type=int, default=5, help="Node-based time-gap baseline B2'")
    args = ap.parse_args()

    in_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Outputs (same schema as your HDFS exports; block_id kept empty)
    b3_path  = outdir / "eventlog_B3_single_trace.csv"
    b2_path  = outdir / f"eventlog_B2_timegap_{args.gap_seconds}s.csv"
    b2n_path = outdir / f"eventlog_B2_node_timegap_{args.node_gap_seconds}s.csv"

    # Stats
    total = 0
    parsed = 0
    top_templates = Counter()

    gap_global = timedelta(seconds=args.gap_seconds)
    gap_node   = timedelta(seconds=args.node_gap_seconds)

    prev_ts = None
    b2_case = 1

    node_prev_ts = {}
    node_case_idx = {}

    def write_header(w):
        # Keep columns consistent with your other pipelines
        w.writerow(["case_id", "activity", "timestamp", "component", "level", "block_id", "node_id"])

    with in_path.open("r", encoding="utf-8", errors="ignore") as f, \
         b3_path.open("w", newline="", encoding="utf-8") as fb3, \
         b2_path.open("w", newline="", encoding="utf-8") as fb2, \
         b2n_path.open("w", newline="", encoding="utf-8") as fb2n:

        w_b3 = csv.writer(fb3)
        w_b2 = csv.writer(fb2)
        w_b2n = csv.writer(fb2n)
        write_header(w_b3); write_header(w_b2); write_header(w_b2n)

        for line in f:
            total += 1
            line = line.strip()
            if not line:
                continue

            # Extract ts2 (the "YYYY-MM-DD-HH.MM.SS.ffffff" token)
            m_ts2 = TS2_RE.search(line)
            if not m_ts2:
                continue

            ts2 = m_ts2.group(0)
            ts = parse_ts2(ts2)
            if ts is None:
                continue

            # Tokenize
            parts = line.split()

            # Heuristic extraction (matches your shown format)
            # parts[0]= "-" or "APPREAD"
            # parts[1]= unix
            # parts[2]= YYYY.MM.DD
            # parts[3]= node (location)
            # parts[4]= ts2
            # parts[5]= node (repeat)
            # parts[6]= RAS
            # parts[7]= component (KERNEL/APP/...)
            # parts[8]= level
            # parts[9:]= message
            node_id = parts[5] if len(parts) > 5 else parts[3] if len(parts) > 3 else "UNKNOWN"
            component = parts[7] if len(parts) > 7 else "UNKNOWN"
            level = parts[8] if len(parts) > 8 and parts[8].upper() in LEVELS else "INFO"
            msg_start = 9 if len(parts) > 9 else len(parts)
            msg = " ".join(parts[msg_start:]) if msg_start < len(parts) else ""

            activity = make_template(msg if msg else line)

            parsed += 1
            top_templates[activity] += 1

            # --- B3: single trace ---
            w_b3.writerow(["case_1", activity, ts.isoformat(sep=" "), component, level, "", node_id])

            # --- B2: global time-gap segmentation ---
            if prev_ts is None:
                b2_case = 1
            else:
                if ts - prev_ts > gap_global:
                    b2_case += 1
            prev_ts = ts
            w_b2.writerow([f"case_{b2_case}", activity, ts.isoformat(sep=" "), component, level, "", node_id])

            # --- B2': node-based time-gap segmentation ---
            last = node_prev_ts.get(node_id)
            if last is None:
                node_case_idx[node_id] = 1
            else:
                if ts - last > gap_node:
                    node_case_idx[node_id] += 1
            node_prev_ts[node_id] = ts
            case_id = f"{node_id}_c{node_case_idx[node_id]}"
            w_b2n.writerow([case_id, activity, ts.isoformat(sep=" "), component, level, "", node_id])

    print("\n=== BGL PIPELINE DONE ===")
    print("Input:", in_path)
    print("Lines read:", total)
    print("Lines parsed:", parsed)
    print("Outputs:")
    print(" -", b3_path)
    print(" -", b2_path)
    print(" -", b2n_path)

    print("\nTop activity templates (first 10):")
    for k, v in top_templates.most_common(10):
        print(f"  {v:>8}  {k}")

if __name__ == "__main__":
    main()
