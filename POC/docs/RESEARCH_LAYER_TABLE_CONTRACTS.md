# Research Layer Table Contracts

This document defines downstream table contracts for the DIAMOND architecture. These are design contracts for future implementation.

## certified_event

Granularity: one row per certified event.

Source:

- `silver_event`
- certified luminosity JSON
- trigger certification metadata

Columns:

```text
event_id
run
luminosityBlock
event
dataset
year
run_period
certified_lumi
certified_trigger
certification_version
selection_version
```

Required logic:

- `certified_lumi = true` only when `(run, luminosityBlock)` is accepted by the certification source.
- `certified_trigger = true` only when the event satisfies the named trigger selection.

## mart_z_to_mumu

Granularity: one row per selected dimuon pair.

Source:

- `certified_event`
- `dimuon`
- `event_summary`

Columns:

```text
event_id
run
luminosityBlock
event
muon1_idx
muon2_idx
muon1_pt
muon2_pt
invariant_mass
delta_r
n_muons
n_jets
MET_pt
HT
ST
z_window
selection_version
```

Required logic:

- Opposite-sign dimuon pair.
- Pair from a certified event.
- Initial Z-window flag: `70 <= invariant_mass <= 110`.

## event_object

Granularity: one row per physics object per event.

Source:

- `silver_muon`
- `silver_jet`
- `silver_met`

Columns:

```text
event_id
object_id
object_type
object_idx
pt
eta
phi
mass
charge
quality_score
source_table
object_version
```

Required logic:

- Stable `object_id = hash(event_id, object_type, object_idx)`.
- MET can be represented as object type `met` with null eta and mass.

## object_pair

Granularity: one row per object pair inside an event.

Source:

- `event_object`

Columns:

```text
event_id
source_object_id
target_object_id
source_type
target_type
delta_eta
delta_phi
delta_r
pt_ratio
pair_mass
charge_product
edge_type
relation_version
```

Required logic:

- Pair each object with later-indexed objects in the same event.
- Compute angular features for objects with eta and phi.
- Use explicit edge types such as `muon_muon`, `muon_jet`, `jet_jet`, `object_met`.

## graph_node

Granularity: one row per graph node.

Source:

- `event_object`

Columns:

```text
event_id
node_id
node_index
node_type
pt
eta
phi
mass
charge
isolation
btag_score
node_feature_version
```

Required logic:

- Node indexes must be dense per event.
- Feature order must be versioned.

## graph_edge

Granularity: one row per graph edge.

Source:

- `object_pair`

Columns:

```text
event_id
source_node_index
target_node_index
edge_type
delta_r
delta_eta
delta_phi
edge_weight
edge_feature_version
```

Required logic:

- Initial edges can be built with `delta_r < 0.4`.
- Later graph variants may include fully connected event graphs.

## candidate_high_st

Granularity: one row per candidate event.

Source:

- `event_summary`

Columns:

```text
event_id
run
luminosityBlock
event
ST
HT
MET_pt
n_muons
n_jets
candidate_rule
threshold_value
score
candidate_version
```

Required logic:

- Initial candidate rule: top percentile of ST in the local dataset.
- Candidate rules must be named and versioned.

## validation_selection_flow

Granularity: one row per cut step.

Source:

- all layers

Columns:

```text
flow_name
step_index
step_name
input_rows
output_rows
rejected_rows
efficiency
cumulative_efficiency
validation_timestamp
```

Required logic:

- Every major physics selection should have a cutflow.
- Counts must be reproducible from saved tables.

