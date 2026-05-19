# Methods (MT3 Prototype)

## Goal

This prototype supports the thesis objective of transforming raw, heterogeneous software system logs into structured event logs and reconstructing traces when explicit correlation identifiers are missing or unreliable.

The main validated MT3 method is a deterministic streaming Smart Trace Construction (STC) heuristic. A DBSCAN-assisted variant is also implemented as an exploratory extension for comparison, but it is not the primary validated method used to define the core STC prototype.

## Event Extraction and Activity Normalization

### Raw Log Parsing

For each raw log line, the pipeline extracts:

- `timestamp`
- `component`
- `level`
- `content`

For HDFS, the parser also extracts:

- `block_id`
- `src_ip`
- `dst_ip`

For BGL, the parser extracts:

- `node_id`

The parsed records are exported as structured event-log CSV files.

### Stable Activity Labels

To reduce noise from variable values, the prototype creates normalized activity labels by masking values such as:

- HDFS block IDs, for example `blk_-...` -> `<BLK>`
- IP addresses -> `<IP>`
- ports -> `<PORT>`
- numeric values -> `<NUM>`
- hexadecimal values in BGL -> `<HEX>`

The normalized message string is used as the event activity name.

## Baseline Trace Construction Methods

Baselines represent simple correlation-weak strategies.

### B3: Single Trace

All events are assigned to one case.

Purpose: show the failure mode when no trace reconstruction is performed.

### B2: Global Time-Gap Segmentation

A new case is started when the time difference between consecutive events in the global stream exceeds a threshold, usually 60 seconds.

Purpose: show that global time-gap segmentation can fail in dense parallel system logs.

### B2': Attribute-Partitioned Time-Gap Segmentation

Events are first split by one available attribute and then segmented by an inactivity gap inside each partition.

- HDFS partition attribute: `component`
- BGL partition attribute: `node_id`

Purpose: provide a stronger baseline than global time-gap segmentation while still using a simple rule.

## Main STC Heuristic

The main MT3 STC implementation reconstructs traces using a deterministic streaming assignment heuristic with an inactivity threshold.

### High-Level Procedure

For each incoming event:

1. Close traces that have been inactive for more than the threshold.
2. Score the event against each currently open trace.
3. Assign the event to the best-scoring trace if the score is positive.
4. Otherwise, create a new trace.

### HDFS Scoring Features

The HDFS STC v2 scoring function uses:

- recent activity history hit
- same component bonus
- same source IP bonus, when available
- same destination IP bonus, when available

### BGL Scoring Features

The BGL STC scoring function uses:

- recent activity history hit
- same component bonus
- same node bonus
- same level bonus

### Key Parameters

- inactivity threshold in seconds
- `K_HISTORY`, the number of recent activities stored per open trace
- feature weights for the scoring bonuses
- maximum number of open traces

## DBSCAN-Assisted Extension

`src/stc_v3_dbscan.py` implements an exploratory DBSCAN-assisted trace reconstruction extension.

The extension:

1. Loads a parsed event log.
2. Splits the stream into temporal segments using an inactivity threshold.
3. Builds feature vectors from relative time, activity, component, level, and optional IP fields.
4. Runs DBSCAN inside bounded temporal segments.
5. Assigns clustered events to reconstructed cases.
6. Assigns DBSCAN noise events conservatively as singleton traces.

This extension is useful for comparison and sensitivity discussion. It should be described as exploratory because the core MT3 thesis prototype is the deterministic streaming STC heuristic.

## Outputs

The pipeline exports event logs as CSV files with columns such as:

- `case_id`
- `activity`
- `timestamp`
- `component`
- `level`
- `block_id`
- `src_ip`
- `dst_ip`
- `node_id`

These CSV files are compatible with PM4Py-based process mining evaluation.
