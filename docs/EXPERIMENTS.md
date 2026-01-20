# Experiments (MT3 Stage)

## Overview
This document describes the MT3-stage experimental design used to evaluate:
- **RQ1 / trace reconstruction quality** (oracle-based where possible)
- **Partial RQ2 / downstream process mining effects** (Inductive Miner + token replay)
- **RQ3 / robustness across datasets** (HDFS + BGL)

The experiments are designed to be computationally feasible and reproducible.

---

## Dataset 1: LogHub HDFS (oracle evaluation possible)
### Input
- Raw log file: `HDFS.log`
- MT3 sample size: 300,000 events

### Oracle case notion
Many HDFS log messages contain a `BlockId` (e.g., `blk_-...`).  
For evaluation only, an **oracle event log** is built where:
- `case_id = BlockId`

This oracle is **not used** by STC during reconstruction in correlation-weak mode; it is only used afterward for evaluation.

---

## Dataset 2: LogHub BGL (robustness, no oracle)
### Input
- `BGL_2k.log` (2,000 events subset)

### Oracle
BGL does not provide a stable ground-truth case identifier comparable to HDFS `BlockId`.
Therefore, oracle purity cannot be computed. Robustness is evaluated via:
- trace statistics (cases, trace length distribution, single-event trace percentage)
- downstream process mining quality (fitness/precision)

---

## Compared methods
### Baselines
- **B3**: single trace (all events → one case)
- **B2**: global time-gap segmentation (e.g., 60s)
- **B2’**: attribute-partitioned time-gap segmentation (Δ=5s)
  - HDFS partition attribute: component
  - BGL partition attribute: node/location

### STC (MT3 implemented)
Deterministic streaming trace construction using:
- inactivity threshold Δ
- similarity scoring with recent activity history + categorical matches

For HDFS, Δ sensitivity is tested: Δ ∈ {2s, 5s, 10s}.  
For BGL, Δ=5s is used for robustness demonstration (consistent with HDFS best MT3 trade-off).

---

## Hypotheses
- **H1**: STC reconstructs traces that align better with oracle grouping (HDFS BlockId) than naïve baselines.
- **H2**: Δ influences reconstruction quality by controlling fragmentation (small Δ) vs merging (large Δ).
- **H3**: A moderate Δ yields better quality than very small or very large Δ on dense HDFS logs.
- **H4 (robustness)**: STC remains applicable on a different log type (BGL), and trace construction choices affect the discovered model quality.

---

## Metrics and outputs
### HDFS trace reconstruction quality (oracle-based)
- average/median/p90 purity
- mixed trace percentage (% traces with purity < 1.0)

Output file:
- `out/purity_table_with_baselines.csv`

### HDFS downstream PM quality (partial RQ2)
Inductive Miner model discovery + token-based replay:
- token-based fitness
- token-based precision

Because full alignment-based evaluation is expensive, MT3 uses a capped subset:
- cap 10 events per case
- max 5000 total events

Output file:
- `out/pm_quality_table_inductive_rq2.csv`

### BGL robustness
- trace statistics table:
  - number of cases, avg/median/max trace length
  - % single-event traces
- downstream PM quality (Inductive Miner + token replay):
  - fitness, precision
  - cap 10 events per case, max 2000 total events (BGL_2k size)

Output files:
- `out_bgl/summary_table_bgl.csv`
- `out_bgl/pm_quality_table_bgl.csv`

---

## Reproducibility notes (MT3)
- Implementations are deterministic (one run per configuration).
- If future versions introduce stochastic clustering, experiments must include repeated runs and variance reporting.
