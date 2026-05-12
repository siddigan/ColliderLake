from __future__ import annotations

from pathlib import Path

from pyspark.sql import DataFrame, SparkSession

from src.lakehouse.config import MuonDbConfig
from src.lakehouse import transforms as T


class MuonDbPipeline:
    """Data engineering ETL for the muon_db lakehouse."""

    def __init__(self, spark: SparkSession, config: MuonDbConfig) -> None:
        self.spark = spark
        self.config = config
        self.output_root = Path(config.output_root)

    def run(self) -> dict[str, int]:
        raw = self.spark.read.parquet(*self._source_parquet_paths())
        bronze = T.project_bronze(raw, self.config).cache()

        outputs: dict[str, DataFrame] = {
            "bronze/bronze_event": T.bronze_event(bronze),
            "bronze/bronze_muon": T.bronze_muon(bronze),
            "bronze/bronze_jet": T.bronze_jet(bronze),
            "bronze/bronze_met": T.bronze_met(bronze),
            "bronze/bronze_trigger": T.bronze_trigger(bronze),
        }

        cleaned = T.clean_events(bronze).cache()
        silver_events = T.silver_event(cleaned).cache()
        silver_muons = T.silver_muon(cleaned).cache()
        silver_jets = T.silver_jet(cleaned).cache()
        silver_met = T.silver_met(cleaned).cache()
        silver_trigger = T.silver_trigger(cleaned)

        outputs.update(
            {
                "silver/silver_event": silver_events,
                "silver/silver_muon": silver_muons,
                "silver/silver_jet": silver_jets,
                "silver/silver_met": silver_met,
                "silver/silver_trigger": silver_trigger,
                "gold/event_summary": T.event_summary(silver_events, silver_muons, silver_jets, silver_met),
                "gold/dimuon": T.dimuon_dataset(silver_muons),
                "gold/jet": T.jet_dataset(silver_jets),
                "gold/met": T.met_dataset(silver_met),
            }
        )

        counts: dict[str, int] = {}
        for name, df in outputs.items():
            counts[name] = df.count()
            self._write_table(df, name)

        bronze.unpersist()
        cleaned.unpersist()
        silver_events.unpersist()
        silver_muons.unpersist()
        silver_jets.unpersist()
        silver_met.unpersist()
        return counts

    def _write_table(self, df: DataFrame, relative_name: str) -> None:
        path = self.output_root / relative_name
        (
            df.write.mode(self.config.write_mode)
            .partitionBy("dataset", "year", "run_period")
            .parquet(str(path))
        )

    def _source_parquet_paths(self) -> list[str]:
        source = self.config.source_parquet
        if "://" in source:
            return [source]

        path = Path(source).expanduser()
        if path.is_file():
            return [path.resolve().as_posix()]
        if not path.exists():
            raise FileNotFoundError(f"Source Parquet path does not exist: {source}")

        files = sorted(file.resolve().as_posix() for file in path.rglob("*.parquet"))
        if not files:
            raise FileNotFoundError(f"No Parquet files found under: {source}")
        return files
