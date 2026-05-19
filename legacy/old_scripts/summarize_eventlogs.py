import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import LabelEncoder, StandardScaler


REQUIRED_COLUMNS = ["activity", "timestamp"]


def load_eventlog(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {missing}")

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).reset_index(drop=True)

    # Preserve original row order for row-by-row oracle comparison.
    df["_original_order"] = np.arange(len(df))

    for col in ["component", "level", "src_ip", "dst_ip", "block_id"]:
        if col not in df.columns:
            df[col] = ""

    df["activity"] = df["activity"].fillna("").astype(str)
    df["component"] = df["component"].fillna("").astype(str)
    df["level"] = df["level"].fillna("").astype(str)
    df["src_ip"] = df["src_ip"].fillna("").astype(str)
    df["dst_ip"] = df["dst_ip"].fillna("").astype(str)
    df["block_id"] = df["block_id"].fillna("").astype(str)

    return df


def encode_series(values: pd.Series) -> np.ndarray:
    values = values.fillna("").astype(str)

    if values.nunique(dropna=False) <= 1:
        return np.zeros(len(values), dtype=float)

    encoded = LabelEncoder().fit_transform(values)
    return encoded.astype(float)


def create_temporal_segments(df: pd.DataFrame, delta_seconds: int) -> pd.DataFrame:
    df = df.sort_values("timestamp").reset_index(drop=True).copy()

    gaps = df["timestamp"].diff().dt.total_seconds().fillna(0)
    new_segment = gaps > delta_seconds
    df["_segment_id"] = new_segment.cumsum().astype(int)

    return df


def split_large_segment(segment: pd.DataFrame, max_segment_size: int) -> list[pd.DataFrame]:
    """
    Split very large temporal segments into smaller chunks to avoid DBSCAN memory errors.
    The split preserves timestamp order.
    """
    segment = segment.sort_values("timestamp").reset_index(drop=True)

    if len(segment) <= max_segment_size:
        return [segment]

    chunks = []
    for start in range(0, len(segment), max_segment_size):
        chunk = segment.iloc[start:start + max_segment_size].copy()
        chunks.append(chunk)

    return chunks


def build_features(segment: pd.DataFrame) -> np.ndarray:
    """
    Build a simple feature representation for DBSCAN.

    Features:
    1. Relative timestamp position inside the temporal segment
    2. Encoded activity label
    3. Encoded component/source
    4. Encoded severity level
    5. Encoded source IP, if available
    6. Encoded destination IP, if available
    """
    t0 = segment["timestamp"].min()
    rel_seconds = (segment["timestamp"] - t0).dt.total_seconds().to_numpy(dtype=float)

    if len(rel_seconds) > 1 and rel_seconds.max() > 0:
        rel_seconds = rel_seconds / rel_seconds.max()
    else:
        rel_seconds = np.zeros(len(segment), dtype=float)

    activity_code = encode_series(segment["activity"])
    component_code = encode_series(segment["component"])
    level_code = encode_series(segment["level"])
    src_code = encode_series(segment["src_ip"])
    dst_code = encode_series(segment["dst_ip"])

    features = np.column_stack(
        [
            rel_seconds,
            activity_code,
            component_code,
            level_code,
            src_code,
            dst_code,
        ]
    )

    return StandardScaler().fit_transform(features)


def assign_singleton_trace(row: pd.Series, case_prefix: str, case_number: int) -> dict:
    row_dict = row.to_dict()
    row_dict["case_id"] = f"{case_prefix}_{case_number}"
    return row_dict


def assign_noise_events(
    result_rows: list[dict],
    noise_events: pd.DataFrame,
    case_prefix: str,
    next_case_number: int,
) -> int:
    """
    Conservative fallback: each DBSCAN noise event becomes its own trace.
    This avoids forcing weakly related events into an artificial cluster.
    """
    for _, row in noise_events.iterrows():
        result_rows.append(assign_singleton_trace(row, case_prefix, next_case_number))
        next_case_number += 1

    return next_case_number


def reconstruct_with_dbscan(
    df: pd.DataFrame,
    delta_seconds: int,
    eps: float,
    min_samples: int,
    case_prefix: str = "stc_dbscan_case",
    max_segment_size: int = 1000,
) -> pd.DataFrame:
    segmented = create_temporal_segments(df, delta_seconds)

    result_rows: list[dict] = []
    next_case_number = 1

    for _, segment in segmented.groupby("_segment_id", sort=True):
        segment = segment.sort_values("timestamp").copy()

        # Large temporal segments can cause DBSCAN memory errors.
        # Therefore, each large segment is split into bounded subsegments.
        subsegments = split_large_segment(segment, max_segment_size)

        for subsegment in subsegments:
            subsegment = subsegment.sort_values("timestamp").copy()

            # Very small segments cannot be meaningfully clustered.
            if len(subsegment) < min_samples:
                for _, row in subsegment.iterrows():
                    result_rows.append(
                        assign_singleton_trace(row, case_prefix, next_case_number)
                    )
                    next_case_number += 1
                continue

            features = build_features(subsegment)

            try:
                labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(features)
            except MemoryError:
                # Conservative fallback if clustering still exceeds memory.
                for _, row in subsegment.iterrows():
                    result_rows.append(
                        assign_singleton_trace(row, case_prefix, next_case_number)
                    )
                    next_case_number += 1
                continue

            subsegment["_dbscan_label"] = labels

            # Cluster labels >= 0 are valid clusters. Label -1 is DBSCAN noise.
            clustered_events = subsegment[subsegment["_dbscan_label"] >= 0]
            for _, cluster_df in clustered_events.groupby("_dbscan_label", sort=True):
                cluster_df = cluster_df.sort_values("timestamp")
                case_id = f"{case_prefix}_{next_case_number}"

                for _, row in cluster_df.iterrows():
                    row_dict = row.to_dict()
                    row_dict["case_id"] = case_id
                    result_rows.append(row_dict)

                next_case_number += 1

            noise_df = subsegment[subsegment["_dbscan_label"] == -1]
            next_case_number = assign_noise_events(
                result_rows=result_rows,
                noise_events=noise_df,
                case_prefix=case_prefix,
                next_case_number=next_case_number,
            )

    result = pd.DataFrame(result_rows)

    if result.empty:
        raise ValueError("No reconstructed events were produced.")

    # Restore original row order so purity scripts can compare row-by-row
    # with out/eventlog_oracle_blockid.csv.
    result = result.sort_values("_original_order").reset_index(drop=True)

    drop_cols = ["_original_order", "_segment_id", "_dbscan_label"]
    result = result.drop(columns=[col for col in drop_cols if col in result.columns])

    preferred_cols = [
        "case_id",
        "activity",
        "timestamp",
        "component",
        "level",
        "block_id",
        "src_ip",
        "dst_ip",
    ]
    remaining_cols = [col for col in result.columns if col not in preferred_cols]
    result = result[[col for col in preferred_cols if col in result.columns] + remaining_cols]

    result["timestamp"] = pd.to_datetime(result["timestamp"]).dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="STC v3: DBSCAN-assisted trace reconstruction."
    )

    parser.add_argument(
        "--input",
        default="out/eventlog_oracle_blockid.csv",
        help="Input parsed event log CSV. Default: out/eventlog_oracle_blockid.csv",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output reconstructed event log CSV. If omitted, a name is generated.",
    )
    parser.add_argument(
        "--delta",
        type=int,
        default=5,
        help="Inactivity threshold in seconds.",
    )
    parser.add_argument(
        "--eps",
        type=float,
        default=0.5,
        help="DBSCAN eps parameter.",
    )
    parser.add_argument(
        "--min_samples",
        type=int,
        default=3,
        help="DBSCAN min_samples parameter.",
    )
    parser.add_argument(
        "--max_segment_size",
        type=int,
        default=1000,
        help="Maximum number of events clustered at once inside a temporal segment.",
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(
            f"out/eventlog_STC_v3_dbscan_delta{args.delta}s_"
            f"eps{args.eps}_min{args.min_samples}_maxseg{args.max_segment_size}.csv"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = load_eventlog(input_path)

    reconstructed = reconstruct_with_dbscan(
        df=df,
        delta_seconds=args.delta,
        eps=args.eps,
        min_samples=args.min_samples,
        max_segment_size=args.max_segment_size,
    )

    reconstructed.to_csv(output_path, index=False)

    trace_lengths = reconstructed.groupby("case_id").size()

    print("\n=== STC v3 DBSCAN DONE ===")
    print("Input:", input_path)
    print("Output:", output_path)
    print("Events:", len(reconstructed))
    print("Traces:", reconstructed["case_id"].nunique())
    print("Average trace length:", round(trace_lengths.mean(), 3))
    print("Median trace length:", round(trace_lengths.median(), 3))
    print("Single-event traces %:", round(trace_lengths.eq(1).mean() * 100, 2))
    print("delta:", args.delta)
    print("eps:", args.eps)
    print("min_samples:", args.min_samples)
    print("max_segment_size:", args.max_segment_size)


if __name__ == "__main__":
    main()