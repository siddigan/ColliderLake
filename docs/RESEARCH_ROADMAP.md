# ColliderLake Research Roadmap

This roadmap moves ColliderLake from a functioning muon lakehouse into a research-grade collider data platform.

## Phase 1: Quality And Cutflows

Goal: make every event selection measurable.

Deliverables:

- `validation_row_counts`
- `validation_selection_flow`
- row-count notebook
- cutflow plot notebook

Research questions:

- How many events are removed by quality flags?
- How many survive the muon trigger?
- How many survive cleaned muon requirements?
- What are the event yield uncertainties introduced by current filters?

## Phase 2: Certification

Goal: align analysis events with official certified luminosity sections.

Deliverables:

- certified luminosity JSON loader
- `certified_lumi`
- `certified_event`
- certification version metadata

Research questions:

- How much event yield changes after certified luminosity filtering?
- Are any high-interest events in non-certified lumisections?

## Phase 3: Physics Marts

Goal: create named, reusable physics selections.

Deliverables:

- `mart_z_to_mumu`
- `mart_high_met_muon`
- `mart_multijet_muon`
- control-region tables

Research questions:

- Does the dimuon mass peak show a clear Z resonance?
- How do event yields vary by jet multiplicity?
- Which regions produce unusual MET and ST tails?

## Phase 4: Topology And Relations

Goal: describe each event as interacting objects.

Deliverables:

- `event_object`
- `object_pair`
- `event_topology_summary`

Research questions:

- What object-pair patterns dominate SingleMuon events?
- Are high-ST events driven by jets, muons, or MET?
- Which angular structures are common in Z-like events?

## Phase 5: Graph-Ready Data

Goal: support graph-learning pipelines while keeping data inspectable.

Deliverables:

- `graph_node`
- `graph_edge`
- `graph_global`
- `graph_event_manifest`

Research questions:

- Which graph construction rule preserves useful physics structure?
- How do sparse delta-R graphs compare with fully connected graphs?
- Can graph summaries separate control and candidate regions?

## Phase 6: Anomaly Candidate Tables

Goal: identify unusual events with deterministic rules before ML.

Deliverables:

- `candidate_high_st`
- `candidate_high_met`
- `candidate_unusual_dimuon`
- `candidate_sparse_region`

Research questions:

- Which events populate extreme ST and MET tails?
- Are unusual events dominated by detector artifacts or real topologies?
- Which candidate rules overlap and which find distinct event classes?

## Phase 7: Feature Registry

Goal: make features versioned and reusable.

Deliverables:

- feature definitions registry
- `feature_event_kinematics`
- `feature_dimuon_resonance`
- `feature_jet_activity`

Research questions:

- Which feature families are stable under selection changes?
- Which features are redundant?
- Which features best describe topology shifts?

## Phase 8: Publication Layer

Goal: freeze reproducible datasets and artifacts.

Deliverables:

- dataset cards
- cutflow reports
- plot manifests
- frozen analysis snapshots

Research questions:

- Can another researcher reproduce the same event yields and plots?
- Are all published outputs traceable to exact source tables and code commits?

