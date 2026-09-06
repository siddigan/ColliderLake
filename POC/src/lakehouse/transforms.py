from __future__ import annotations

from functools import reduce

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from src.lakehouse.config import (
    BRONZE_COLUMNS,
    EVENT_COLUMNS,
    JET_COLUMNS,
    MET_COLUMNS,
    MUON_COLUMNS,
    QUALITY_COLUMNS,
    TRIGGER_COLUMNS,
    MuonDbConfig,
)


def has_column(df: DataFrame, name: str) -> bool:
    return name in df.columns


def col_or_null(df: DataFrame, name: str):
    return F.col(name) if has_column(df, name) else F.lit(None).alias(name)


def bool_col_or_default(df: DataFrame, name: str, default: bool = False):
    return F.coalesce(F.col(name).cast("boolean"), F.lit(default)) if has_column(df, name) else F.lit(default)


def array_col_or_empty(df: DataFrame, name: str):
    return F.col(name) if has_column(df, name) else F.array()


def with_lakehouse_metadata(df: DataFrame, config: MuonDbConfig) -> DataFrame:
    return (
        df.withColumn("dataset", F.lit(config.dataset))
        .withColumn("dataset_path", F.lit(config.dataset_path))
        .withColumn("year", F.lit(config.year))
        .withColumn("run_period", F.lit(config.run_period))
        .withColumn("nanoaod_version", F.lit(config.nanoaod_version))
        .withColumn("source_file", F.input_file_name())
        .withColumn("ingested_at_utc", F.current_timestamp())
    )


def with_event_id(df: DataFrame) -> DataFrame:
    return df.withColumn(
        "event_id",
        F.sha2(
            F.concat_ws(
                ":",
                F.col("dataset"),
                F.col("year").cast("string"),
                F.col("run").cast("string"),
                F.col("luminosityBlock").cast("string"),
                F.col("event").cast("string"),
            ),
            256,
        ),
    )


def project_bronze(raw: DataFrame, config: MuonDbConfig) -> DataFrame:
    selected = [col_or_null(raw, name).alias(name) for name in BRONZE_COLUMNS]
    return with_event_id(with_lakehouse_metadata(raw.select(*selected), config))


def bronze_event(bronze: DataFrame) -> DataFrame:
    return bronze.select(
        "event_id",
        *EVENT_COLUMNS,
        "dataset",
        "dataset_path",
        "year",
        "run_period",
        "nanoaod_version",
        "source_file",
        "ingested_at_utc",
    )


def bronze_muon(bronze: DataFrame) -> DataFrame:
    return bronze.select("event_id", *EVENT_COLUMNS, *MUON_COLUMNS, "dataset", "year", "run_period")


def bronze_jet(bronze: DataFrame) -> DataFrame:
    return bronze.select("event_id", *EVENT_COLUMNS, *JET_COLUMNS, "dataset", "year", "run_period")


def bronze_met(bronze: DataFrame) -> DataFrame:
    return bronze.select("event_id", *EVENT_COLUMNS, *MET_COLUMNS, "dataset", "year", "run_period")


def bronze_trigger(bronze: DataFrame) -> DataFrame:
    return bronze.select("event_id", *EVENT_COLUMNS, *TRIGGER_COLUMNS, *QUALITY_COLUMNS, "dataset", "year", "run_period")


def clean_events(bronze: DataFrame) -> DataFrame:
    good_vertices = bool_col_or_default(bronze, "Flag_goodVertices", default=True)
    met_filters = bool_col_or_default(bronze, "Flag_METFilters", default=True)
    iso_mu24 = bool_col_or_default(bronze, "HLT_IsoMu24", default=False)
    mu50 = bool_col_or_default(bronze, "HLT_Mu50", default=False)

    return (
        bronze.withColumn("good_vertices", good_vertices)
        .withColumn("met_filters_pass", met_filters)
        .withColumn("hlt_iso_mu24", iso_mu24)
        .withColumn("hlt_mu50", mu50)
        .filter(F.col("good_vertices") & F.col("met_filters_pass") & F.col("hlt_iso_mu24"))
    )


def silver_event(cleaned: DataFrame) -> DataFrame:
    return cleaned.select(
        "event_id",
        "run",
        "luminosityBlock",
        "event",
        "dataset",
        "year",
        "run_period",
        "good_vertices",
        "met_filters_pass",
        "hlt_iso_mu24",
        "hlt_mu50",
    )


def silver_trigger(cleaned: DataFrame) -> DataFrame:
    return cleaned.select(
        "event_id",
        "run",
        "luminosityBlock",
        "event",
        "dataset",
        "year",
        "run_period",
        "hlt_iso_mu24",
        "hlt_mu50",
        "good_vertices",
        "met_filters_pass",
    )


def silver_met(cleaned: DataFrame) -> DataFrame:
    return cleaned.select(
        "event_id",
        "run",
        "luminosityBlock",
        "event",
        F.col("MET_pt").cast("double").alias("met_pt"),
        F.col("MET_phi").cast("double").alias("met_phi"),
        F.col("PuppiMET_pt").cast("double").alias("puppi_met_pt"),
        "dataset",
        "year",
        "run_period",
    )


def _arrays_zip_struct(df: DataFrame, mapping: dict[str, str]):
    return F.arrays_zip(*[array_col_or_empty(df, source).alias(target) for source, target in mapping.items()])


def silver_muon(cleaned: DataFrame) -> DataFrame:
    mapping = {
        "Muon_pt": "pt",
        "Muon_eta": "eta",
        "Muon_phi": "phi",
        "Muon_mass": "mass",
        "Muon_charge": "charge",
        "Muon_tightId": "tight_id",
        "Muon_pfRelIso04_all": "isolation",
    }
    exploded = cleaned.select(
        "event_id",
        "run",
        "luminosityBlock",
        "event",
        "dataset",
        "year",
        "run_period",
        F.posexplode_outer(_arrays_zip_struct(cleaned, mapping)).alias("muon_idx", "muon"),
    )
    return (
        exploded.filter(F.col("muon").isNotNull())
        .select(
            "event_id",
            "run",
            "luminosityBlock",
            "event",
            F.col("muon_idx").cast("int").alias("muon_idx"),
            F.col("muon.pt").cast("double").alias("pt"),
            F.col("muon.eta").cast("double").alias("eta"),
            F.col("muon.phi").cast("double").alias("phi"),
            F.col("muon.mass").cast("double").alias("mass"),
            F.col("muon.charge").cast("int").alias("charge"),
            F.col("muon.isolation").cast("double").alias("isolation"),
            F.col("muon.tight_id").cast("boolean").alias("tight_id"),
            "dataset",
            "year",
            "run_period",
        )
        .filter((F.col("tight_id") == F.lit(True)) & (F.col("isolation") < F.lit(0.15)) & (F.col("pt") > F.lit(20.0)))
    )


def silver_jet(cleaned: DataFrame) -> DataFrame:
    mapping = {
        "Jet_pt": "pt",
        "Jet_eta": "eta",
        "Jet_phi": "phi",
        "Jet_mass": "mass",
        "Jet_btagDeepB": "btag_deep_b",
    }
    exploded = cleaned.select(
        "event_id",
        "run",
        "luminosityBlock",
        "event",
        "dataset",
        "year",
        "run_period",
        F.posexplode_outer(_arrays_zip_struct(cleaned, mapping)).alias("jet_idx", "jet"),
    )
    return (
        exploded.filter(F.col("jet").isNotNull())
        .select(
            "event_id",
            "run",
            "luminosityBlock",
            "event",
            F.col("jet_idx").cast("int").alias("jet_idx"),
            F.col("jet.pt").cast("double").alias("pt"),
            F.col("jet.eta").cast("double").alias("eta"),
            F.col("jet.phi").cast("double").alias("phi"),
            F.col("jet.mass").cast("double").alias("mass"),
            F.col("jet.btag_deep_b").cast("double").alias("btag_deep_b"),
            "dataset",
            "year",
            "run_period",
        )
        .filter(F.col("pt").isNotNull() & (F.col("pt") > F.lit(0.0)))
    )


def event_summary(events: DataFrame, muons: DataFrame, jets: DataFrame, met: DataFrame) -> DataFrame:
    muon_agg = muons.groupBy("event_id").agg(
        F.count("*").cast("int").alias("n_muons"),
        F.max("pt").alias("leading_muon_pt"),
        F.sum("pt").alias("muon_ht"),
    )
    jet_agg = jets.groupBy("event_id").agg(
        F.count("*").cast("int").alias("n_jets"),
        F.max("pt").alias("leading_jet_pt"),
        F.sum("pt").alias("ht"),
    )
    return (
        events.join(muon_agg, "event_id", "left")
        .join(jet_agg, "event_id", "left")
        .join(met.select("event_id", "met_pt", "met_phi", "puppi_met_pt"), "event_id", "left")
        .fillna({"n_muons": 0, "n_jets": 0, "muon_ht": 0.0, "ht": 0.0})
        .withColumn("n_electrons", F.lit(None).cast("int"))
        .withColumn("n_taus", F.lit(None).cast("int"))
        .withColumn("st", F.coalesce(F.col("ht"), F.lit(0.0)) + F.coalesce(F.col("muon_ht"), F.lit(0.0)) + F.coalesce(F.col("met_pt"), F.lit(0.0)))
        .select(
            "event_id",
            "run",
            "luminosityBlock",
            "event",
            "dataset",
            "year",
            "run_period",
            "n_muons",
            "n_jets",
            "n_electrons",
            "n_taus",
            "leading_muon_pt",
            "leading_jet_pt",
            F.col("met_pt").alias("MET_pt"),
            F.col("ht").alias("HT"),
            F.col("st").alias("ST"),
        )
    )


def _delta_phi(left, right):
    raw = F.abs(left - right)
    return F.when(raw > F.lit(3.141592653589793), F.lit(6.283185307179586) - raw).otherwise(raw)


def dimuon_dataset(muons: DataFrame) -> DataFrame:
    m1 = muons.alias("m1")
    m2 = muons.alias("m2")
    pairs = m1.join(
        m2,
        (F.col("m1.event_id") == F.col("m2.event_id")) & (F.col("m1.muon_idx") < F.col("m2.muon_idx")),
        "inner",
    )
    dphi = _delta_phi(F.col("m1.phi"), F.col("m2.phi"))
    deta = F.col("m1.eta") - F.col("m2.eta")
    # Massless-safe four-vector reconstruction using pt, eta, phi, and rest mass.
    e1 = F.sqrt((F.col("m1.pt") * F.cosh(F.col("m1.eta"))) ** 2 + F.col("m1.mass") ** 2)
    e2 = F.sqrt((F.col("m2.pt") * F.cosh(F.col("m2.eta"))) ** 2 + F.col("m2.mass") ** 2)
    px = F.col("m1.pt") * F.cos(F.col("m1.phi")) + F.col("m2.pt") * F.cos(F.col("m2.phi"))
    py = F.col("m1.pt") * F.sin(F.col("m1.phi")) + F.col("m2.pt") * F.sin(F.col("m2.phi"))
    pz = F.col("m1.pt") * F.sinh(F.col("m1.eta")) + F.col("m2.pt") * F.sinh(F.col("m2.eta"))
    mass2 = (e1 + e2) ** 2 - px ** 2 - py ** 2 - pz ** 2
    return pairs.select(
        F.col("m1.event_id").alias("event_id"),
        F.col("m1.run").alias("run"),
        F.col("m1.luminosityBlock").alias("luminosityBlock"),
        F.col("m1.event").alias("event"),
        F.col("m1.dataset").alias("dataset"),
        F.col("m1.year").alias("year"),
        F.col("m1.run_period").alias("run_period"),
        F.col("m1.muon_idx").alias("muon1_idx"),
        F.col("m2.muon_idx").alias("muon2_idx"),
        F.greatest(F.col("m1.pt"), F.col("m2.pt")).alias("muon1_pt"),
        F.least(F.col("m1.pt"), F.col("m2.pt")).alias("muon2_pt"),
        F.sqrt(F.greatest(mass2, F.lit(0.0))).alias("invariant_mass"),
        F.sqrt(deta ** 2 + dphi ** 2).alias("delta_r"),
        (F.col("m1.charge") * F.col("m2.charge") < F.lit(0)).alias("opposite_sign"),
    ).filter(F.col("opposite_sign") == F.lit(True))


def jet_dataset(jets: DataFrame) -> DataFrame:
    return jets.select(
        "event_id",
        "run",
        "luminosityBlock",
        "event",
        "dataset",
        "year",
        "run_period",
        "jet_idx",
        "pt",
        "eta",
        "phi",
        "mass",
        "btag_deep_b",
    )


def met_dataset(met: DataFrame) -> DataFrame:
    return met.select(
        "event_id",
        "run",
        "luminosityBlock",
        "event",
        "dataset",
        "year",
        "run_period",
        "met_pt",
        "met_phi",
        "puppi_met_pt",
    )

