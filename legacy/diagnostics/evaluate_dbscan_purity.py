from pathlib import Path
import pandas as pd


ORACLE = Path("out/eventlog_oracle_blockid.csv")

CANDIDATES = [
    Path("out/eventlog_STC_v3_dbscan_delta2s_eps0.2_min3_maxseg1000.csv"),
    Path("out/eventlog_STC_v3_dbscan_delta5s_eps0.2_min3_maxseg1000.csv"),
    Path("out/eventlog_STC_v3_dbscan_delta10s_eps0.2_min3_maxseg1000.csv"),
]


def evaluate(candidate_path: Path) -> dict:
    oracle = pd.read_csv(ORACLE)
    candidate = pd.read_csv(candidate_path)

    if len(oracle) != len(candidate):
        raise ValueError(
            f"Row mismatch: oracle={len(oracle)}, candidate={len(candidate)}"
        )

    if "block_id" not in oracle.columns:
        raise ValueError("Oracle file must contain block_id column.")

    if "case_id" not in candidate.columns:
        raise ValueError("Candidate file must contain case_id column.")

    df = pd.DataFrame({
        "oracle_case": oracle["block_id"].astype(str),
        "reconstructed_case": candidate["case_id"].astype(str),
    })

    trace_stats = []

    for case_id, group in df.groupby("reconstructed_case"):
        counts = group["oracle_case"].value_counts()
        majority_count = counts.iloc[0]
        total_count = len(group)
        purity = majority_count / total_count
        mixed = counts.size > 1

        trace_stats.append({
            "case_id": case_id,
            "trace_len": total_count,
            "majority_count": majority_count,
            "unique_oracle_cases": counts.size,
            "purity": purity,
            "mixed": mixed,
        })

    stats = pd.DataFrame(trace_stats)

    return {
        "file": candidate_path.name,
        "events": len(df),
        "traces": len(stats),
        "avg_trace_len": stats["trace_len"].mean(),
        "median_trace_len": stats["trace_len"].median(),
        "single_event_pct": (stats["trace_len"].eq(1).mean() * 100),
        "avg_purity": stats["purity"].mean(),
        "median_purity": stats["purity"].median(),
        "p90_purity": stats["purity"].quantile(0.90),
        "mixed_trace_pct": (stats["mixed"].mean() * 100),
    }


def main():
    rows = []
    for path in CANDIDATES:
        if not path.exists():
            print(f"Missing: {path}")
            continue
        rows.append(evaluate(path))

    result = pd.DataFrame(rows)
    print(result.to_string(index=False))

    out_path = Path("out/dbscan_purity_summary.csv")
    result.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()