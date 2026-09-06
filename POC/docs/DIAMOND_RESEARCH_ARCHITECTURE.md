# DIAMOND Research Architecture

DIAMOND is the downstream research architecture for ColliderLake. It extends the current bronze, silver, and gold lakehouse into a physics research platform that can support rigorous analysis, reproducible datasets, graph construction, anomaly search, and publication-grade outputs.

DIAMOND stands for:

```text
D - Detector and data-quality certification
I - Inference-ready physics features
A - Analysis marts and event selections
M - Multi-object relations and graph structures
O - Observability, validation, and lineage
N - Novelty and anomaly candidate stores
D - Dissemination-ready datasets and reports
```

The current implemented lakehouse ends at:

```text
ROOT -> converted Parquet -> bronze -> silver -> gold
```

DIAMOND starts after gold:

```text
gold curated datasets
  -> certified physics layer
  -> analysis marts
  -> relation and graph layer
  -> research feature layer
  -> anomaly candidate layer
  -> validation and provenance layer
  -> publication layer
```

## Design Principles

1. Physics correctness before modeling.
2. Every selection must be expressed as a named, versioned contract.
3. Derived features must record their formula, source tables, and selection scope.
4. Analysis datasets should be immutable once published.
5. Model-ready data must remain traceable back to run, luminosity block, event, and source file.
6. Plots and notebooks are outputs, not sources of truth.

## Layer 0: Existing Lakehouse

Already implemented:

- `bronze_*`: raw selected NanoAOD projections.
- `silver_*`: cleaned event, muon, jet, MET, and trigger tables.
- `event_summary`: one row per cleaned event.
- `dimuon`: opposite-sign cleaned muon pairs.
- `jet`: curated jet table.
- `met`: curated MET table.

This is the stable base for downstream research.

## Layer 1: Certified Physics Layer

Purpose: turn cleaned events into certified analysis-ready events.

Planned tables:

```text
certified_event
certified_lumi
certified_trigger
certified_object_summary
```

Business logic:

- Apply CMS golden JSON luminosity certification.
- Track run and luminosity-block acceptance.
- Keep only events in certified luminosity sections.
- Version trigger menus and trigger selection logic.
- Preserve rejected-event counts for auditability.

Key research value:

- Separates detector/data certification from later analysis choices.
- Makes published event counts reproducible.

## Layer 2: Physics Selection Marts

Purpose: create named event selections for concrete physics channels.

Planned tables:

```text
mart_single_muon_baseline
mart_z_to_mumu
mart_high_met_muon
mart_multijet_muon
mart_control_regions
mart_signal_like_regions
```

Example logic:

- `mart_z_to_mumu`: exactly two or more cleaned muons, at least one opposite-sign pair, dimuon mass near Z window.
- `mart_high_met_muon`: single cleaned muon, high MET, event passes certified luminosity and trigger.
- `mart_multijet_muon`: cleaned muon event with high jet multiplicity and HT.

Key research value:

- Enables repeatable analysis regions.
- Keeps selection definitions explicit instead of buried in notebook cells.

## Layer 3: Multi-Object Relation Layer

Purpose: represent event topology between reconstructed objects.

Planned tables:

```text
event_object
object_pair
muon_jet_relation
muon_met_relation
jet_jet_relation
event_topology_summary
```

Business logic:

- Convert each physics object into a typed row: muon, jet, MET proxy, future electron/photon/tau.
- Build pairwise relations inside each event.
- Compute `delta_eta`, `delta_phi`, `delta_r`, pT ratio, mass combinations, and charge compatibility.
- Keep relation edge types explicit.

Key research value:

- Provides the bridge between tabular physics analysis and graph construction.
- Makes event topology queryable with SQL before any GNN work.

## Layer 4: Research Feature Layer

Purpose: store deterministic, reproducible feature tables for analysis and modeling.

Planned tables:

```text
feature_event_kinematics
feature_muon_quality
feature_jet_activity
feature_dimuon_resonance
feature_event_shape
feature_selection_flags
```

Feature groups:

- Event kinematics: MET, HT, ST, object multiplicities.
- Resonance features: dimuon mass, delta R, leading/subleading pT, Z-window flags.
- Jet activity: n-jets, leading jet pT, b-tag summaries.
- Event shape: centrality, sphericity-like proxies, balance variables.
- Selection flags: baseline, control-region, signal-like-region booleans.

Key research value:

- Keeps features deterministic and versioned.
- Avoids mixing feature generation with model training.

## Layer 5: Graph-Ready Layer

Purpose: materialize graph data structures while remaining lakehouse-native.

Planned tables:

```text
graph_node
graph_edge
graph_global
graph_event_manifest
```

Graph design:

- Node: one row per object per event.
- Edge: one row per relation between objects in an event.
- Global: one row per event with event-level context.
- Manifest: graph version, selection version, and source table references.

Node types:

```text
muon
jet
met
electron
photon
tau
```

Initial implementation should support muon, jet, and MET because those are already available.

Key research value:

- Enables GNN pipelines without forcing graph logic into notebooks.
- Keeps graph construction reproducible and inspectable.

## Layer 6: Novelty And Anomaly Candidate Layer

Purpose: capture unusual events as data products before modeling.

Planned tables:

```text
candidate_high_st
candidate_high_met
candidate_unusual_dimuon
candidate_sparse_region
candidate_score_registry
```

Initial non-ML candidate logic:

- High ST tail events.
- High MET tail events.
- Dimuon mass away from known resonance windows.
- Events in sparse bins of `n_muons`, `n_jets`, `HT`, `MET`.

Later model-driven logic:

- Autoencoder scores.
- Isolation forest scores.
- Density estimate scores.
- Graph anomaly scores.

Key research value:

- Lets the project explore anomaly detection without starting with opaque models.
- Creates human-reviewable event candidate tables.

## Layer 7: Validation And Observability Layer

Purpose: verify every ETL and research layer.

Planned tables:

```text
validation_row_counts
validation_selection_flow
validation_feature_ranges
validation_schema_versions
validation_plot_manifest
lineage_dataset_version
```

Validation checks:

- Row-count transitions between layers.
- Null and range checks for physics features.
- Invariant mass range checks.
- Duplicate event checks.
- Partition completeness.
- Selection flow cut tables.

Key research value:

- Makes failures visible before conclusions are drawn.
- Produces the cutflow tables expected in physics analysis.

## Layer 8: Publication Layer

Purpose: freeze analysis-ready outputs for reports, papers, talks, and demos.

Planned outputs:

```text
publication/cutflows/
publication/tables/
publication/plots/
publication/notebook_exports/
publication/dataset_cards/
```

Publication products:

- Dataset cards.
- Cutflow summaries.
- Z mass peak plots.
- Event yield tables.
- Candidate event tables.
- Reproducibility manifest.

Key research value:

- Separates exploratory work from stable public artifacts.
- Makes research claims traceable to exact data versions.

## Immediate Next Build Order

Recommended next implementation sequence:

1. Add validation and cutflow tables.
2. Add certified luminosity scaffolding.
3. Add physics selection marts.
4. Add object relation tables.
5. Add graph-ready node and edge tables.
6. Add deterministic anomaly candidate tables.
7. Add dataset cards and publication manifests.

This order keeps the work physics-grounded and avoids building advanced modeling layers before the data contracts are reliable.

