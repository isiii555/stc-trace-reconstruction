# Methods (MT3 Prototype)

## Goal
This prototype supports the thesis objective of transforming raw, heterogeneous software system logs into structured **event logs** and reconstructing **traces (cases)** when explicit correlation identifiers are missing or unreliable.

The implemented work focuses on the **MT3 prototype** version of Smart Trace Construction (STC), which is a deterministic streaming heuristic. The full STC method described conceptually in the thesis also mentions clustering-based grouping (e.g., DBSCAN) as a possible option, but clustering is not implemented in the MT3 prototype.

## Event extraction and activity normalization
### Raw log parsing
For each raw log line, the pipeline extracts:
- **timestamp**
- **component** (logger / subsystem identifier)
- **severity level**
- **content** (message body)

This produces a structured event record suitable for further processing.

### Stable activity labels (template normalization)
To reduce noise from variable values (IDs, IPs, numbers), the prototype creates a normalized **activity label** by masking:
- block IDs (e.g., `blk_-...`) → `<BLK>`
- IP addresses → `<IP>`
- ports → `<PORT>`
- numbers → `<NUM>`

The normalized message string is used as the event’s **activity name**.

## Baseline trace construction methods
Baselines represent simple correlation-weak strategies.

### B3: single trace
All events are assigned to one case.  
Purpose: show the failure mode when no case reconstruction is performed.

### B2: global time-gap segmentation
A new case is started when the time difference between consecutive events in the global stream exceeds a threshold (e.g., 60s).  
Purpose: show that global time-gap segmentation fails in dense parallel system logs (often produces one long trace).

### B2’: attribute-partitioned time-gap segmentation
Events are first split by a single available attribute (e.g., **component** in HDFS or **node/location** in BGL), and then segmented by an inactivity gap Δ within each partition.  
Purpose: a stronger baseline, but it often produces extreme fragmentation (many single-event traces) or extreme imbalance.

## STC (MT3 implemented heuristic)
The MT3 prototype reconstructs traces using a **streaming assignment heuristic** with an inactivity threshold Δ.

### High-level idea
Maintain a set of “open traces”. For each incoming event:
1) Close traces that have been inactive for more than Δ  
2) Score the event against each currently open trace  
3) Assign the event to the best-scoring trace (if score > 0), otherwise create a new trace

### Similarity scoring (implemented features)
The MT3 scoring function uses simple, interpretable signals:
- **history hit bonus**: event activity appears in the trace’s recent activity history (`K_history`)
- **same component bonus**
- **same source IP bonus** (if available)
- **same destination IP bonus** (if available)

The heuristic is deterministic and intended as an MT3 feasibility implementation.

### Key parameters (MT3)
- Δ: inactivity threshold (seconds) controlling fragmentation vs merging
- `K_history`: number of recent activities stored per trace
- weights for history/component/src/dst bonuses

## Outputs
The pipeline exports event logs as CSV:
- `case_id, activity, timestamp, component, level, ...`
These CSV files are compatible with process mining tooling (including conversion in PM4Py).
