# Smart Trace Construction (STC)

This repository contains prototype for trace reconstruction from correlation-weak software system logs.

The prototype is general in design: it transforms software system logs into process-mining-ready event logs using Smart Trace Construction. HDFS and BGL are implemented evaluation profiles used in the thesis. Other logs can be supported by adding a parser/profile or by mapping structured CSV columns such as timestamp, activity, and component.

It includes:

- Raw log parsing and activity normalization into event-log CSV files.
- Baseline trace construction methods: B3, B2, and B2'.
- Main STC deterministic streaming heuristic for HDFS.
- BGL robustness pipeline.
- Exploratory DBSCAN-assisted STC extension.
- Evaluation scripts for HDFS oracle purity and downstream process mining quality.

## Project Structure

- `src/` - main thesis/demo scripts.
- `scripts/` - PowerShell run wrappers for the main experiment order.
- `legacy/old_scripts/` - older prototypes and stale scripts kept for reference.
- `legacy/diagnostics/` - scratch and diagnostic scripts kept for reference.
- `docs/` - method, metric, and experiment notes.
- `results/` - optional small final tables for thesis or defense use.
- `data/` - local datasets, ignored by Git.
- `out/` - local generated HDFS outputs, ignored by Git.
- `out_bgl/` - local generated BGL outputs, ignored by Git.
- `out_generic/` - local generated generic raw-log demo outputs, ignored by Git.

## Datasets

Download the datasets separately and place them locally as:

- `data/HDFS_v1/HDFS.log`
- `data/BGL/BGL_2k.log`

The repository may contain local copies on your machine, but `data/` is ignored by Git and should not be committed.

## Environment

Tested with Python 3.x and Windows PowerShell.

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

If PowerShell cannot find Python or uses the Microsoft Store alias, set `$PythonExe` at the top of the run script to the full `python.exe` path.

## Desktop Demo Launcher

Start the simple Tkinter launcher with:

```powershell
python app/stc_desktop_app.py
```

The launcher runs the existing PowerShell scripts and streams command output into the window. It does not change the STC algorithms or result calculations.

For the thesis defense video launcher, run:

```powershell
pip install customtkinter
python app/stc_demo_app.py
```

BPMN/Petri net visualization is optional and used only for demonstration. The script tries to generate a BPMN image first and falls back to a Petri net image if BPMN is unavailable. The main thesis evaluation is based on trace reconstruction metrics and token-based fitness/precision tables.

## Generic Raw Log Demo

The prototype includes a general raw-log demo mode:

```powershell
python src/run_pipeline_generic.py --input "<selected_log_file>" --delta 60 --mode correlation_weak
```

or through PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo_generic.ps1 -InputFile "<selected_log_file>" -Mode correlation_weak
```

The generic mode tries to parse common raw log formats using recognizable timestamps and message text. It supports common timestamp styles such as ISO timestamps, syslog-style timestamps, Apache error-log timestamps, and Apache access-log timestamps.

This mode does not guarantee support for every log format. If parsing fails, the system reports that the format is unsupported. In that case, provide structured CSV input or add a custom parser/profile for that log family.

Generic mode is for demonstration and extensibility. The evaluated thesis experiments remain the HDFS and BGL profiles.

Generic reconstruction supports two modes. `correlation_weak` ignores detected identifiers during grouping and is used when correlation attributes are missing or intentionally ignored. `attribute_based` is used when the log contains detectable correlation attributes, such as block ID, request ID, session ID, trace ID, or transaction ID. Attribute-based mode is a generic/demo extension and is not presented as the main thesis result.

When generic parsing succeeds, the demo also attempts downstream process mining and optional BPMN/Petri net visualization for the selected log. These generic outputs are for demonstration only and are not part of the thesis evaluation tables.

Generic mode can also calculate HDFS-like oracle purity metrics when it detects an oracle-like identifier in a meaningful share of parsed events. Supported identifiers include HDFS `blk_...` block IDs and fields such as `request_id=...`, `session_id=...`, `trace_id=...`, `transaction_id=...`, and `case_id=...`. If none of these identifiers are detected, the generic summary reports only trace statistics and skips purity metrics.

If a generic run reports `PermissionError` or `Permission denied` while saving a CSV, close any open result CSV files in Excel or another viewer and run again. The generic pipeline also tries to save the new run with a timestamped filename when the default output file is locked.

## Defense Demo Commands

For a narrated console demo, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo_hdfs.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\demo_bgl.ps1
```

## Main HDFS Run Order

Run the full HDFS pipeline with:

```powershell
.\scripts\run_all_hdfs.ps1
```

Equivalent manual commands:

```powershell
python src/run_pipeline_raw.py --input data/HDFS_v1/HDFS.log
python src/baseline_component_timegap.py
python src/stc_v2_history_ip.py --delta 2
python src/stc_v2_history_ip.py --delta 5
python src/stc_v2_history_ip.py --delta 10
python src/stc_v3_dbscan.py --input out/eventlog_oracle_blockid.csv --delta 5 --eps 0.2 --min_samples 3 --max_segment_size 1000
python src/purity_table_with_baselines.py
python src/pm_quality_eval.py
```

The HDFS run generates the STC v2 delta sensitivity files required by the thesis purity table:

- `out/eventlog_STC_v2_history_ip_delta2s.csv`
- `out/eventlog_STC_v2_history_ip_delta5s.csv`
- `out/eventlog_STC_v2_history_ip_delta10s.csv`

Main HDFS result tables:

- `out/purity_table_with_baselines.csv`
- `out/pm_quality_table_inductive_rq2.csv`

## Main BGL Run Order

Run the full BGL robustness pipeline with:

```powershell
.\scripts\run_all_bgl.ps1
```

Equivalent manual commands:

```powershell
python src/run_pipeline_bgl.py --input data/BGL/BGL_2k.log
python src/stc_bgl_v1_history_ip.py
python src/summarize_eventlogs_bgl.py
python src/pm_quality_eval_bgl_rq3.py
```

Main BGL result tables:

- `out_bgl/summary_table_bgl.csv`
- `out_bgl/pm_quality_table_bgl.csv`

## DBSCAN Extension

DBSCAN-assisted STC is implemented as an exploratory extension, not as the main validated STC method.

Run the default extension command with:

```powershell
.\scripts\run_dbscan_extension.ps1
```

Equivalent manual command:

```powershell
python src/stc_v3_dbscan.py --input out/eventlog_oracle_blockid.csv --delta 5 --eps 0.2 --min_samples 3 --max_segment_size 1000
```

The main comparison table includes the DBSCAN extension when the expected DBSCAN output file exists:

- `out/eventlog_STC_v3_dbscan_delta5s_eps0.2_min3_maxseg1000.csv`
- `out/purity_table_with_baselines.csv`

## Main Thesis Scripts

Keep these scripts in `src/` for the final defense demo:

- `src/run_pipeline_raw.py`
- `src/baseline_component_timegap.py`
- `src/stc_v2_history_ip.py`
- `src/stc_v3_dbscan.py`
- `src/purity_table_with_baselines.py`
- `src/pm_quality_eval.py`
- `src/run_pipeline_bgl.py`
- `src/stc_bgl_v1_history_ip.py`
- `src/summarize_eventlogs_bgl.py`
- `src/pm_quality_eval_bgl_rq3.py`

## Notes on Generated Files

Do not commit raw datasets, full generated event logs, or local output folders.

The folders `data/`, `out/`, and `out_bgl/` are ignored by Git. Small final CSV tables may be copied into `results/` when they are ready for thesis writing or defense slides.
