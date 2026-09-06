from pathlib import Path


def test_poc_preserves_legacy_entrypoints():
    assert Path("POC/scripts/run_lakehouse_etl.py").exists()
    assert Path("POC/src/lakehouse/pipeline.py").exists()
    bootstrap = Path("POC/scripts/_bootstrap.py").read_text(encoding="utf-8")
    assert "parents[1]" in bootstrap
