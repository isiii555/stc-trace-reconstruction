# Smart Trace Construction (STC) – MT3 Prototype (HDFS + BGL)

This repository contains an MT3-stage prototype for **trace reconstruction from correlation-weak software system logs**.
It includes:
- Log parsing + normalization into event logs (CSV)
- Baseline trace construction methods (B2/B2’/B3)
- STC heuristic trace construction (streaming, deterministic)
- Evaluation: oracle-based trace purity (HDFS) and downstream PM quality via Inductive Miner (token replay)

## Project structure
- `src/` – all scripts
- `data/` – datasets (not tracked in Git; user provides locally)
- `out/`, `out_bgl/` – generated event logs + evaluation tables (not tracked)

## Datasets
You must download datasets yourself:
- **LogHub HDFS** raw log: `HDFS.log`
- **LogHub BGL** sample: `BGL_2k.log` (a small subset used for robustness)

Place them as:
- `data/HDFS_v1/HDFS.log`
- `data/BGL/BGL_2k.log`

## Environment
Tested with Python 3.x and Windows PowerShell.

Install dependencies:
```bash
python -m pip install -r requirements.txt
