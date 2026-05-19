import argparse
import csv
import re
from collections import deque
from datetime import datetime
from pathlib import Path

import pandas as pd


ISO_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)
APACHE_ERROR_RE = re.compile(
    r"\[(?P<ts>[A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4})\]"
)
SYSLOG_RE = re.compile(r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\b")
APACHE_ACCESS_RE = re.compile(r"(?P<ts>\d{1,2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2})")

SEVERITY_RE = re.compile(
    r"\b(INFO|WARN|WARNING|ERROR|DEBUG|TRACE|CRITICAL|NOTICE)\b",
    re.IGNORECASE,
)
COMPONENT_PATTERNS = [
    re.compile(r"\b(?:component|logger|module|service)=([A-Za-z0-9_.:-]+)", re.IGNORECASE),
    re.compile(r"\[([A-Za-z0-9_.:-]{3,})\]"),
    re.compile(r"\b([A-Za-z0-9_.-]+):\s+"),
]

IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
PATH_RE = re.compile(r"(?:(?:[A-Za-z]:\\|/)[^\s,;:]+(?:[\\/][^\s,;:]+)*)")
HEX_ID_RE = re.compile(r"\b(?:0x[0-9a-fA-F]+|[0-9a-fA-F]{12,}|[A-Za-z0-9_-]{24,})\b")
NUM_RE = re.compile(r"\b\d+\b")
SPACE_RE = re.compile(r"\s+")
HDFS_BLOCK_RE = re.compile(r"\bblk_-?\d+(?:_\d+)?\b", re.IGNORECASE)
ORACLE_KV_RE = re.compile(
    r"\b(?:request_id|session_id|trace_id|transaction_id|case_id)\s*=\s*([A-Za-z0-9_.:-]+)",
    re.IGNORECASE,
)
GENERIC_MODES = ("correlation_weak", "attribute_based")
ACCEPTED_GENERIC_MODES = (*GENERIC_MODES, "id_aware")

UNSUPPORTED_MESSAGE = (
    "Unsupported log format: the system could not reliably extract timestamps and messages. "
    "Please provide a log with recognizable timestamps or use structured CSV input."
)


def save_csv_with_fallback(df: pd.DataFrame, target_path: Path, **to_csv_kwargs) -> Path:
    try:
        df.to_csv(target_path, **to_csv_kwargs)
        return target_path
    except PermissionError as exc:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fallback_path = target_path.with_name(f"{target_path.stem}_{stamp}{target_path.suffix}")
        print(f"Could not overwrite {target_path}: {type(exc).__name__}: {exc}")
        print(f"The file may be open in Excel or another viewer. Saving this run to: {fallback_path}")
        df.to_csv(fallback_path, **to_csv_kwargs)
        return fallback_path


def parse_timestamp(raw_ts: str, fmt: str) -> datetime | None:
    try:
        if fmt == "iso":
            value = raw_ts.replace("T", " ").replace(",", ".")
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        if fmt == "apache_error":
            return datetime.strptime(raw_ts, "%a %b %d %H:%M:%S %Y")
        if fmt == "syslog":
            parsed = datetime.strptime(raw_ts, "%b %d %H:%M:%S")
            return parsed.replace(year=datetime.now().year)
        if fmt == "apache_access":
            return datetime.strptime(raw_ts, "%d/%b/%Y:%H:%M:%S")
    except ValueError:
        return None
    return None


def find_timestamp(line: str) -> tuple[datetime, tuple[int, int]] | tuple[None, None]:
    patterns = [
        (ISO_RE, "iso"),
        (APACHE_ERROR_RE, "apache_error"),
        (APACHE_ACCESS_RE, "apache_access"),
        (SYSLOG_RE, "syslog"),
    ]
    for pattern, fmt in patterns:
        match = pattern.search(line)
        if not match:
            continue
        ts = parse_timestamp(match.group("ts"), fmt)
        if ts is not None:
            return ts, match.span("ts")
    return None, None


def clean_message(line: str, ts_span: tuple[int, int]) -> str:
    before = line[: ts_span[0]]
    after = line[ts_span[1] :]
    message = f"{before} {after}"
    message = message.replace("[]", " ")
    message = message.strip(" \t-[]")
    message = SPACE_RE.sub(" ", message).strip()
    return message


def detect_severity(text: str) -> str:
    match = SEVERITY_RE.search(text)
    if not match:
        return ""
    value = match.group(1).upper()
    return "WARN" if value == "WARNING" else value


def detect_component(message: str) -> str:
    for pattern in COMPONENT_PATTERNS:
        match = pattern.search(message)
        if match:
            component = match.group(1).strip("[]:")
            if component and not SEVERITY_RE.fullmatch(component):
                return component[:80]
    return "generic"


def detect_oracle_case(text: str) -> str:
    block_match = HDFS_BLOCK_RE.search(text)
    if block_match:
        return block_match.group(0)

    kv_match = ORACLE_KV_RE.search(text)
    if kv_match:
        return kv_match.group(1)

    return ""


def make_activity(message: str) -> str:
    text = PATH_RE.sub("<PATH>", message)
    text = IP_RE.sub("<IP>", text)
    text = HEX_ID_RE.sub("<ID>", text)
    text = NUM_RE.sub("<NUM>", text)
    text = SPACE_RE.sub(" ", text).strip()
    return text[:180] if text else "generic_event"


def parse_raw_log(input_path: Path) -> list[dict]:
    rows = []
    non_empty = 0
    parsed = 0

    with input_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            non_empty += 1

            timestamp, ts_span = find_timestamp(line)
            if timestamp is None or ts_span is None:
                continue

            message = clean_message(line, ts_span)
            if not message:
                continue

            severity = detect_severity(message)
            component = detect_component(message)
            oracle_case = detect_oracle_case(line)
            activity = make_activity(message)

            rows.append(
                {
                    "timestamp": timestamp.isoformat(sep=" "),
                    "severity": severity,
                    "message": message,
                    "component": component,
                    "raw_message": line,
                    "activity": activity,
                    "oracle_case": oracle_case,
                    "line_no": line_no,
                }
            )
            parsed += 1

    success_rate = parsed / non_empty if non_empty else 0.0
    print(f"Non-empty lines: {non_empty}")
    print(f"Parsed events: {parsed}")
    print(f"Parsing success rate: {success_rate:.2%}")

    if non_empty == 0 or success_rate < 0.70:
        print(UNSUPPORTED_MESSAGE)
        return []

    return rows


def event_oracle_case(event: dict) -> str:
    return str(event.get("oracle_case") or "").strip()


def normalize_mode(mode: str) -> str:
    if mode == "id_aware":
        print("Warning: --mode id_aware is deprecated; using --mode attribute_based instead.")
        return "attribute_based"
    return mode


def reconstruct_traces(
    df: pd.DataFrame,
    delta_seconds: int,
    mode: str,
    max_trace_len: int,
    max_trace_duration: int,
) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    open_traces = {}
    trace_ids = []
    next_trace_id = 1
    delta = pd.Timedelta(seconds=delta_seconds)
    max_duration = pd.Timedelta(seconds=max_trace_duration)
    oracle_available = df["oracle_case"].fillna("").astype(str).str.strip().ne("").any()
    attribute_based_active = mode == "attribute_based" and oracle_available

    if mode == "attribute_based" and oracle_available:
        print("Generic reconstruction mode: attribute_based")
        print("Detected correlation attributes will be used as a strong grouping feature.")
    elif mode == "attribute_based":
        print("Generic reconstruction mode: attribute_based")
        print("No oracle-like IDs found for grouping; falling back to correlation_weak behavior.")
    else:
        print("Generic reconstruction mode: correlation_weak")
        print("Detected oracle-like IDs are ignored during grouping in this mode.")
    print(f"Max trace length: {max_trace_len}")
    print(f"Max trace duration seconds: {max_trace_duration}")

    def score(event, trace):
        value = 0.0
        event_oracle = event_oracle_case(event)
        if attribute_based_active and event_oracle and event_oracle == trace["oracle_case"]:
            value += 10.0
        if event["activity"] in trace["history"]:
            value += 2.0
        if event["component"] == trace["component"]:
            value += 1.0
        if event["severity"] and event["severity"] == trace["severity"]:
            value += 0.5
        return value

    def compatible(event, trace):
        ts = event["timestamp"]
        if trace["length"] >= max_trace_len:
            return False
        if ts - trace["start_ts"] > max_duration:
            return False

        if not attribute_based_active:
            return True

        event_oracle = event_oracle_case(event)
        trace_oracle = trace["oracle_case"]
        if event_oracle or trace_oracle:
            return event_oracle == trace_oracle
        return True

    for event in df.to_dict("records"):
        ts = event["timestamp"]
        oracle_case = event_oracle_case(event) if attribute_based_active else ""

        inactive = [tid for tid, trace in open_traces.items() if ts - trace["last_ts"] > delta]
        for tid in inactive:
            del open_traces[tid]

        best_tid = None
        best_score = -1.0
        for tid, trace in open_traces.items():
            if not compatible(event, trace):
                continue
            current_score = score(event, trace)
            if current_score > best_score:
                best_score = current_score
                best_tid = tid

        if best_tid is None or best_score <= 0.0:
            trace_id = f"generic_{next_trace_id}"
            next_trace_id += 1
            open_traces[trace_id] = {
                "start_ts": ts,
                "last_ts": ts,
                "component": event["component"],
                "severity": event["severity"],
                "history": deque([event["activity"]], maxlen=5),
                "length": 1,
                "oracle_case": oracle_case,
            }
        else:
            trace_id = best_tid
            trace = open_traces[trace_id]
            trace["last_ts"] = ts
            trace["component"] = event["component"]
            trace["severity"] = event["severity"]
            trace["history"].append(event["activity"])
            trace["length"] += 1

        trace_ids.append(trace_id)

    df["case_id"] = trace_ids
    return df


def has_meaningful_oracle(df: pd.DataFrame) -> tuple[bool, float]:
    if "oracle_case" not in df.columns or len(df) == 0:
        return False, 0.0

    coverage = df["oracle_case"].fillna("").astype(str).str.strip().ne("").mean()
    return coverage > 0.0, float(coverage)


def calculate_purity_metrics(df: pd.DataFrame) -> dict:
    oracle_df = df.copy()
    oracle_df["oracle_case"] = oracle_df["oracle_case"].fillna("").astype(str).str.strip()
    oracle_df = oracle_df[oracle_df["oracle_case"] != ""]
    if oracle_df.empty:
        return {}

    purities = []
    mixed = []
    for _, group in oracle_df.groupby("case_id", sort=False):
        counts = group["oracle_case"].value_counts()
        purities.append(float(counts.iloc[0]) / len(group))
        mixed.append(counts.size > 1)

    if not purities:
        return {}

    purity_series = pd.Series(purities)
    return {
        "oracle_coverage_pct": round(100.0 * len(oracle_df) / len(df), 2) if len(df) else 0.0,
        "avg_purity": round(float(purity_series.mean()), 4),
        "median_purity": round(float(purity_series.median()), 4),
        "p90_purity": round(float(purity_series.quantile(0.90)), 4),
        "mixed_trace_pct": round(100.0 * sum(mixed) / len(mixed), 2) if mixed else 0.0,
    }


def summarize(df: pd.DataFrame, mode: str, delta_seconds: int) -> pd.DataFrame:
    trace_lengths = df.groupby("case_id").size()
    single_event_pct = 100.0 * trace_lengths.eq(1).mean() if len(trace_lengths) else 0.0
    row = {
        "method": "Generic STC",
        "mode": mode,
        "delta": delta_seconds,
        "events": len(df),
        "cases": df["case_id"].nunique(),
        "avg_trace_len": round(float(trace_lengths.mean()), 3) if len(trace_lengths) else 0.0,
        "median_trace_len": round(float(trace_lengths.median()), 3) if len(trace_lengths) else 0.0,
        "max_trace_len": int(trace_lengths.max()) if len(trace_lengths) else 0,
        "single_event_pct": round(single_event_pct, 2),
    }

    oracle_available, oracle_coverage = has_meaningful_oracle(df)
    if oracle_available:
        print("Oracle-like identifier detected: purity metrics will be calculated.")
        print(f"Oracle-like identifier coverage: {oracle_coverage:.2%}")
        row.update(calculate_purity_metrics(df))
    else:
        print("No oracle-like identifier detected: only trace statistics will be reported.")
        if "oracle_case" in df.columns and len(df):
            print(f"Oracle-like identifier coverage: {oracle_coverage:.2%}")

    return pd.DataFrame(
        [row]
    )


def to_pm4py_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    pm_df = df[["case_id", "activity", "timestamp"]].copy()
    pm_df["timestamp"] = pd.to_datetime(pm_df["timestamp"], errors="coerce")
    pm_df = pm_df.dropna(subset=["case_id", "activity", "timestamp"])
    pm_df = pm_df.rename(
        columns={
            "case_id": "case:concept:name",
            "activity": "concept:name",
            "timestamp": "time:timestamp",
        }
    )
    return pm_df.sort_values(["case:concept:name", "time:timestamp"]).reset_index(drop=True)


def evaluate_process_mining(df: pd.DataFrame, outdir: Path) -> Path | None:
    try:
        import pm4py
        from pm4py.objects.conversion.log import converter as log_converter
        from pm4py.objects.log.util import dataframe_utils
    except ImportError as exc:
        print("Generic process mining evaluation skipped: PM4Py is not available.")
        print(f"Full error: {type(exc).__name__}: {exc}")
        return None

    try:
        pm_df = to_pm4py_dataframe(df)
        pm_df = pm_df.groupby("case:concept:name", sort=False).head(10).head(2000).copy()
        cases_used = pm_df["case:concept:name"].nunique()
        events_used = len(pm_df)

        pm_df = dataframe_utils.convert_timestamp_columns_in_df(pm_df)
        log = log_converter.apply(pm_df, variant=log_converter.Variants.TO_EVENT_LOG)

        print("Discovering generic process model for token-based fitness/precision...")
        net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(log)
        fitness = pm4py.fitness_token_based_replay(log, net, initial_marking, final_marking)["log_fitness"]
        precision = pm4py.precision_token_based_replay(log, net, initial_marking, final_marking)

        out = pd.DataFrame(
            [
                {
                    "method": "Generic STC",
                    "cases_used": int(cases_used),
                    "events_used": int(events_used),
                    "fitness": round(float(fitness), 4),
                    "precision": round(float(precision), 4),
                    "eval_type": "token",
                    "cap_per_case": 10,
                    "cap_total_events": 2000,
                }
            ]
        )
        out_path = outdir / "pm_quality_table_generic.csv"
        out_path = save_csv_with_fallback(out, out_path, index=False)
        print(f"Saved generic process mining table: {out_path}")
        print(out.to_string(index=False))
        return out_path
    except Exception as exc:
        print("Generic process mining evaluation skipped after an error.")
        print("This does not affect generic trace reconstruction outputs.")
        print(f"Full error: {type(exc).__name__}: {exc}")
        return None


def simplify_activities_for_visualization(df: pd.DataFrame) -> pd.DataFrame:
    sample = df.copy()
    activities = list(sample["activity"].drop_duplicates())
    mapping = {activity: f"A{idx:03d}" for idx, activity in enumerate(activities, start=1)}
    sample["activity"] = sample["activity"].map(mapping)
    print(f"Generic visualization activity labels simplified: {len(mapping)} unique activities")
    return sample


def save_visualization(visualizer, visualization, output_path: Path) -> bool:
    try:
        if hasattr(visualization, "format"):
            visualization.format = output_path.suffix.lstrip(".")
        visualizer.save(visualization, str(output_path))
        print(f"Saved generic process model visualization: {output_path}")
        return True
    except Exception as exc:
        print(f"Could not save {output_path}: {type(exc).__name__}: {exc}")
        return False


def visualize_process_model(df: pd.DataFrame, outdir: Path) -> Path | None:
    try:
        import pm4py
    except ImportError as exc:
        print("Generic process model visualization skipped: PM4Py is not available.")
        print(f"Full error: {type(exc).__name__}: {exc}")
        return None

    try:
        sample = df.sort_values(["case_id", "timestamp"]).copy()
        selected_cases = list(sample["case_id"].drop_duplicates().head(30))
        sample = sample[sample["case_id"].isin(selected_cases)]
        sample = sample.groupby("case_id", sort=False).head(10).head(300).copy()
        sample = simplify_activities_for_visualization(sample)

        pm_df = to_pm4py_dataframe(sample)
        from pm4py.objects.conversion.log import converter as log_converter
        from pm4py.objects.log.util import dataframe_utils

        pm_df = dataframe_utils.convert_timestamp_columns_in_df(pm_df)
        log = log_converter.apply(pm_df, variant=log_converter.Variants.TO_EVENT_LOG)

        try:
            from pm4py.visualization.bpmn import visualizer as bpmn_visualizer

            if hasattr(pm4py, "discover_bpmn_inductive"):
                model = pm4py.discover_bpmn_inductive(log)
            elif hasattr(pm4py, "discover_process_tree_inductive") and hasattr(pm4py, "convert_to_bpmn"):
                model = pm4py.convert_to_bpmn(pm4py.discover_process_tree_inductive(log))
            else:
                model = None

            if model is not None:
                visualization = bpmn_visualizer.apply(model)
                png_path = outdir / "process_model_generic_bpmn.png"
                svg_path = outdir / "process_model_generic_bpmn.svg"
                saved_png = save_visualization(bpmn_visualizer, visualization, png_path)
                saved_svg = save_visualization(bpmn_visualizer, visualization, svg_path)
                if saved_png:
                    print("Generic BPMN visualization generated.")
                    return png_path
                if saved_svg:
                    print("Generic BPMN visualization generated.")
                    return svg_path
        except Exception as exc:
            print("Generic BPMN visualization unavailable; trying Petri net fallback.")
            print(f"Full error: {type(exc).__name__}: {exc}")

        from pm4py.visualization.petri_net import visualizer as pn_visualizer

        net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(log)
        visualization = pn_visualizer.apply(net, initial_marking, final_marking)
        png_path = outdir / "process_model_generic_petri.png"
        svg_path = outdir / "process_model_generic_petri.svg"
        saved_png = save_visualization(pn_visualizer, visualization, png_path)
        saved_svg = save_visualization(pn_visualizer, visualization, svg_path)
        if saved_png:
            print("Generic Petri net fallback visualization generated.")
            return png_path
        if saved_svg:
            print("Generic Petri net fallback visualization generated.")
            return svg_path

        print("Generic process model visualization could not be generated.")
        return None
    except Exception as exc:
        print("Generic process model visualization skipped after an error.")
        print("This does not affect generic trace reconstruction outputs.")
        print(f"Full error: {type(exc).__name__}: {exc}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Generic raw log parser and STC demo pipeline.")
    parser.add_argument("--input", required=True, help="Path to a raw log file.")
    parser.add_argument("--delta", type=int, default=60, help="Inactivity threshold in seconds.")
    parser.add_argument(
        "--mode",
        choices=ACCEPTED_GENERIC_MODES,
        default="correlation_weak",
        help="Generic reconstruction mode. Default: correlation_weak.",
    )
    parser.add_argument("--max_trace_len", type=int, default=100, help="Maximum events per reconstructed trace.")
    parser.add_argument(
        "--max_trace_duration",
        type=int,
        default=120,
        help="Maximum reconstructed trace duration in seconds.",
    )
    args = parser.parse_args()
    args.mode = normalize_mode(args.mode)

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    outdir = Path("out_generic")
    outdir.mkdir(parents=True, exist_ok=True)

    print("Generic raw log mode uses best-effort parsing.")
    print("This mode is for demo/extensibility and is not part of the evaluated thesis experiments.")
    print(f"Input file: {input_path}")
    print(f"Delta seconds: {args.delta}")
    print(f"Reconstruction mode: {args.mode}")

    rows = parse_raw_log(input_path)
    if not rows:
        raise SystemExit(1)

    prepared = pd.DataFrame(rows)
    prepared_path = outdir / "eventlog_generic_prepared.csv"
    prepared_path = save_csv_with_fallback(prepared, prepared_path, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Saved prepared event log: {prepared_path}")

    reconstructed = reconstruct_traces(
        prepared,
        delta_seconds=args.delta,
        mode=args.mode,
        max_trace_len=args.max_trace_len,
        max_trace_duration=args.max_trace_duration,
    )
    reconstructed_path = outdir / f"eventlog_STC_generic_{args.mode}_delta{args.delta}s.csv"
    reconstructed_path = save_csv_with_fallback(reconstructed, reconstructed_path, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Saved reconstructed event log: {reconstructed_path}")

    summary = summarize(reconstructed, mode=args.mode, delta_seconds=args.delta)
    summary_path = outdir / "summary_table_generic.csv"
    summary_path = save_csv_with_fallback(summary, summary_path, index=False)
    print(f"Saved generic summary table: {summary_path}")
    print(summary.to_string(index=False))
    evaluate_process_mining(reconstructed, outdir)
    visualize_process_model(reconstructed, outdir)


if __name__ == "__main__":
    main()
