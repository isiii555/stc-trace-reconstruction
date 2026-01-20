import re
import csv
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

# Extract src/dest IPs when present
SRC_RE = re.compile(r"src:\s*/?(\d{1,3}(?:\.\d{1,3}){3})")
DEST_RE = re.compile(r"dest:\s*/?(\d{1,3}(?:\.\d{1,3}){3})")

# Example line:
# 081109 203518 143 INFO dfs.DataNode$DataXceiver: Receiving block blk_-1608... src: /10.250...
LINE_RE = re.compile(
    r'^(?P<Date>\d{6})\s+(?P<Time>\d{6})\s+(?P<Pid>\d+)\s+'
    r'(?P<Level>[A-Z]+)\s+(?P<Component>[^:]+):\s+(?P<Content>.*)$'
)

BLOCK_RE = re.compile(r'(blk_-?\d+)')
IP_RE = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b')
PORT_RE = re.compile(r':\d+\b')
NUM_RE = re.compile(r'\b\d+\b')

def parse_ts(mmddyy: str, hhmmss: str) -> datetime:
    # HDFS uses MMDDYY and HHMMSS
    return datetime.strptime(mmddyy + hhmmss, "%m%d%y%H%M%S")

def make_template(content: str) -> str:
    # Simple normalization (MT3-friendly)
    s = content
    s = BLOCK_RE.sub("<BLK>", s)
    s = IP_RE.sub("<IP>", s)
    s = PORT_RE.sub(":<PORT>", s)
    s = NUM_RE.sub("<NUM>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:180]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to raw HDFS.log")
    ap.add_argument("--outdir", default="out", help="Output folder")
    ap.add_argument("--gap_seconds", type=int, default=60, help="Time-gap for baseline B2 (global stream, very naive)")
    ap.add_argument("--max_lines", type=int, default=300000,
                    help="Stop after N lines for quick runs. Use 0 for full file.")
    args = ap.parse_args()

    in_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    oracle_path = outdir / "eventlog_oracle_blockid.csv"
    b3_path = outdir / "eventlog_B3_single_trace.csv"
    b2_path = outdir / f"eventlog_B2_timegap_{args.gap_seconds}s.csv"

    # Stats
    total = 0
    parsed = 0
    with_block = 0
    with_src = 0
    with_dst = 0
    unique_blocks = set()
    top_templates = Counter()

    gap = timedelta(seconds=args.gap_seconds)
    b2_case = 1
    prev_ts = None

    def write_header(w):
        w.writerow(["case_id", "activity", "timestamp", "component", "level", "block_id", "src_ip", "dst_ip"])

    with in_path.open("r", encoding="utf-8", errors="ignore") as f, \
         oracle_path.open("w", newline="", encoding="utf-8") as fo, \
         b3_path.open("w", newline="", encoding="utf-8") as fb3, \
         b2_path.open("w", newline="", encoding="utf-8") as fb2:

        w_oracle = csv.writer(fo)
        w_b3 = csv.writer(fb3)
        w_b2 = csv.writer(fb2)

        write_header(w_oracle)
        write_header(w_b3)
        write_header(w_b2)

        for line in f:
            total += 1
            if args.max_lines and total > args.max_lines:
                break

            line = line.strip()
            if not line:
                continue

            m = LINE_RE.match(line)
            if not m:
                continue

            d = m.groupdict()
            try:
                ts = parse_ts(d["Date"], d["Time"])
            except Exception:
                continue

            content = d["Content"]
            component = d["Component"].strip()
            level = d["Level"].strip()

            bm = BLOCK_RE.search(content)
            block_id = bm.group(1) if bm else ""

            srcm = SRC_RE.search(content)
            dstm = DEST_RE.search(content)
            src_ip = srcm.group(1) if srcm else ""
            dst_ip = dstm.group(1) if dstm else ""

            activity = make_template(content)

            parsed += 1
            top_templates[activity] += 1

            if block_id:
                with_block += 1
                if len(unique_blocks) < 2_000_000:
                    unique_blocks.add(block_id)

            if src_ip:
                with_src += 1
            if dst_ip:
                with_dst += 1

            # Oracle: group by block_id if present
            oracle_case = block_id if block_id else "NO_BLOCK"
            w_oracle.writerow([oracle_case, activity, ts.isoformat(sep=" "), component, level, block_id, src_ip, dst_ip])

            # B3: single case
            w_b3.writerow(["case_1", activity, ts.isoformat(sep=" "), component, level, block_id, src_ip, dst_ip])

            # B2: global time-gap segmentation (very naive)
            if prev_ts is None:
                b2_case = 1
            else:
                if ts - prev_ts > gap:
                    b2_case += 1
            prev_ts = ts
            w_b2.writerow([f"case_{b2_case}", activity, ts.isoformat(sep=" "), component, level, block_id, src_ip, dst_ip])

    print("\n=== DONE ===")
    print("Input file:", in_path)
    print("Lines read:", total)
    print("Lines parsed:", parsed)
    print("Events with block_id:", with_block, f"({(with_block/parsed*100 if parsed else 0):.2f}%)")
    print("Events with src_ip:", with_src, f"({(with_src/parsed*100 if parsed else 0):.2f}%)")
    print("Events with dst_ip:", with_dst, f"({(with_dst/parsed*100 if parsed else 0):.2f}%)")
    print("Unique block_ids (sampled):", len(unique_blocks))
    print("Outputs:")
    print(" -", oracle_path)
    print(" -", b3_path)
    print(" -", b2_path)

    print("\nTop activity templates (first 10):")
    for k, v in top_templates.most_common(10):
        print(f"  {v:>8}  {k}")

if __name__ == "__main__":
    main()
