from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchLayer:
    order: int
    name: str
    purpose: str
    planned_tables: tuple[str, ...]


DIAMOND_LAYERS: tuple[ResearchLayer, ...] = (
    ResearchLayer(
        order=1,
        name="certified_physics",
        purpose="Apply luminosity certification, trigger certification, and auditable event quality constraints.",
        planned_tables=("certified_event", "certified_lumi", "certified_trigger", "certified_object_summary"),
    ),
    ResearchLayer(
        order=2,
        name="physics_marts",
        purpose="Create named analysis selections for reusable physics channels and control regions.",
        planned_tables=(
            "mart_single_muon_baseline",
            "mart_z_to_mumu",
            "mart_high_met_muon",
            "mart_multijet_muon",
            "mart_control_regions",
        ),
    ),
    ResearchLayer(
        order=3,
        name="object_relations",
        purpose="Represent event topology through objects and pairwise relations.",
        planned_tables=("event_object", "object_pair", "muon_jet_relation", "jet_jet_relation", "event_topology_summary"),
    ),
    ResearchLayer(
        order=4,
        name="research_features",
        purpose="Store deterministic event, object, resonance, and topology features.",
        planned_tables=(
            "feature_event_kinematics",
            "feature_muon_quality",
            "feature_jet_activity",
            "feature_dimuon_resonance",
            "feature_event_shape",
        ),
    ),
    ResearchLayer(
        order=5,
        name="graph_ready",
        purpose="Materialize graph nodes, edges, globals, and graph manifests in lakehouse-native form.",
        planned_tables=("graph_node", "graph_edge", "graph_global", "graph_event_manifest"),
    ),
    ResearchLayer(
        order=6,
        name="anomaly_candidates",
        purpose="Capture deterministic and later model-driven unusual-event candidates.",
        planned_tables=(
            "candidate_high_st",
            "candidate_high_met",
            "candidate_unusual_dimuon",
            "candidate_sparse_region",
            "candidate_score_registry",
        ),
    ),
    ResearchLayer(
        order=7,
        name="validation_observability",
        purpose="Track row counts, cutflows, schema versions, feature ranges, and plot manifests.",
        planned_tables=(
            "validation_row_counts",
            "validation_selection_flow",
            "validation_feature_ranges",
            "validation_schema_versions",
            "validation_plot_manifest",
        ),
    ),
    ResearchLayer(
        order=8,
        name="publication",
        purpose="Freeze dataset cards, cutflows, plots, candidate tables, and reproducibility manifests.",
        planned_tables=("dataset_cards", "cutflow_reports", "plot_manifest", "frozen_analysis_snapshots"),
    ),
)


def research_layer_rows() -> list[dict[str, object]]:
    return [
        {
            "order": layer.order,
            "name": layer.name,
            "purpose": layer.purpose,
            "planned_tables": ", ".join(layer.planned_tables),
        }
        for layer in DIAMOND_LAYERS
    ]

