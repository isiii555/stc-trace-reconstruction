# Metrics

## Trace purity (oracle-based, HDFS)
Purity measures how consistent a reconstructed trace is with respect to an oracle case notion.

Let σ be a reconstructed trace, and let each event in σ have an oracle label b (HDFS: BlockId).
Define:

purity(σ) = (max_b count_σ(b)) / |σ|

Where:
- count_σ(b) = number of events in σ whose oracle label is b
- |σ| = number of events in σ

Interpretation:
- purity(σ) = 1.0 means the reconstructed trace contains events from exactly one oracle case
- purity(σ) < 1.0 indicates mixing of multiple oracle cases

### Aggregation
Reported over all reconstructed traces:
- average purity
- median purity
- 90th percentile purity (p90)

### Mixed trace percentage
A trace is “mixed” if purity(σ) < 1.0

mixed_trace_pct = 100 * (# mixed traces) / (# all traces)

---

## Downstream process mining quality (MT3 partial RQ2)
### Model discovery
A process model is discovered from each event log using **Inductive Miner** (Petri net output).

### Evaluation type (MT3)
For feasibility at MT3, **token-based replay** metrics are used:
- token-based fitness
- token-based precision

These are computed using PM4Py’s token replay utilities.

### Why not “generalization” and “simplicity” in MT3?
- Generalization often requires cross-validation or larger stable logs to avoid misleading results.
- Simplicity requires additional model-structure analysis and consistent discovery settings across datasets.
- With event capping (for MT3 feasibility), generalization/simplicity may be unstable.

Therefore, MT3 reports fitness and precision as an initial downstream signal.
Generalization and simplicity can be added in the next stage after trace construction stabilizes and larger logs are evaluated.
