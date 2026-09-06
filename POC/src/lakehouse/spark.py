from __future__ import annotations

import os
from pathlib import Path
import sys
from urllib.request import urlretrieve

from pyspark.sql import SparkSession

BARE_LOCAL_FS_VERSION = "0.1.0"
BARE_LOCAL_FS_JAR = f"hadoop-bare-naked-local-fs-{BARE_LOCAL_FS_VERSION}.jar"
BARE_LOCAL_FS_URL = (
    "https://repo1.maven.org/maven2/com/globalmentor/hadoop-bare-naked-local-fs/"
    f"{BARE_LOCAL_FS_VERSION}/{BARE_LOCAL_FS_JAR}"
)


def create_spark(app_name: str = "muon_db_etl") -> SparkSession:
    """Create a local Spark session suitable for Parquet lakehouse transforms."""
    _configure_windows_java_home()
    _configure_pyspark_python()

    builder = (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.sql.shuffle.partitions", "8")
    )

    if os.name == "nt":
        bare_fs_jar = _ensure_bare_local_fs_jar()
        builder = (
            builder.config("spark.driver.extraClassPath", str(bare_fs_jar))
            .config("spark.executor.extraClassPath", str(bare_fs_jar))
        )

    spark = builder.getOrCreate()
    if os.name == "nt":
        spark.sparkContext._jsc.hadoopConfiguration().set(  # noqa: SLF001
            "fs.file.impl", "com.globalmentor.apache.hadoop.fs.BareLocalFileSystem"
        )
    return spark


def _configure_windows_java_home() -> None:
    """Use a common Temurin JDK install when Java is installed but not on PATH."""
    if os.name != "nt" or os.environ.get("JAVA_HOME"):
        return

    adoptium_root = Path("C:/Program Files/Eclipse Adoptium")
    if not adoptium_root.exists():
        return

    candidates = sorted(adoptium_root.glob("jdk-*-hotspot"), reverse=True)
    if not candidates:
        return

    java_home = candidates[0]
    os.environ["JAVA_HOME"] = str(java_home)
    os.environ["PATH"] = f"{java_home / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"


def _configure_pyspark_python() -> None:
    scripts_dir = Path(sys.executable).resolve().parent
    os.environ["PATH"] = f"{scripts_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    # Use python.exe from PATH on Windows to avoid Spark command-line parsing issues with spaces in paths.
    python_command = "python.exe" if os.name == "nt" else sys.executable
    os.environ.setdefault("PYSPARK_PYTHON", python_command)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", python_command)


def _ensure_bare_local_fs_jar() -> Path:
    workspace_root = Path(__file__).resolve().parents[2]
    jar_dir = workspace_root / ".spark-jars"
    jar_dir.mkdir(parents=True, exist_ok=True)
    jar_path = jar_dir / BARE_LOCAL_FS_JAR
    if not jar_path.exists():
        urlretrieve(BARE_LOCAL_FS_URL, jar_path)
    return jar_path
