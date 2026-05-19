# Results Folder

This folder is reserved for small final tables that may be copied from generated outputs for thesis writing or defense slides.

Generated event logs and large intermediate files should stay in `out/` and `out_bgl/`. Those folders are local working outputs and are intentionally ignored by Git.

Recommended final tables to copy here when needed:

- `out/purity_table_with_baselines.csv` - HDFS baseline, STC v2, and DBSCAN purity/trace statistics.
- `out/pm_quality_table_inductive_rq2.csv` - HDFS downstream process mining fitness and precision.
- `out_bgl/summary_table_bgl.csv` - BGL robustness trace statistics.
- `out_bgl/pm_quality_table_bgl.csv` - BGL downstream process mining fitness and precision.
- `out/dbscan_purity_summary.csv` - optional DBSCAN sensitivity/diagnostic summary, if used in appendix material.

Only copy final, presentation-ready CSV tables here. Do not copy raw logs, full event logs, or dataset files.
