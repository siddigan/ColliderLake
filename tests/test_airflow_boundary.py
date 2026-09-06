from pathlib import Path


def test_src_does_not_import_airflow():
    for path in Path("src").rglob("*.py"):
        assert "airflow" not in path.read_text(encoding="utf-8").lower(), path
