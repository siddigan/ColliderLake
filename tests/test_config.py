import shutil
from pathlib import Path

import pytest

from src.utils.config import (
    fit_config_id,
    load_yaml,
    selection_files,
    selection_for_dataset,
    selection_id,
    validate_selection,
)


def test_selection_id_is_stable():
    selection = load_yaml("configs/selections/resonance_ladder_2012.yaml")
    assert selection_id(selection) == selection_id(selection)
    assert len(selection_id(selection)) == 8


def test_selection_id_changes_when_cut_changes():
    selection = load_yaml("configs/selections/resonance_ladder_2012.yaml")
    changed = {
        **selection,
        "muon": {
            **selection["muon"],
            "pt_min": selection["muon"]["pt_min"] + 1.0,
        },
    }
    assert selection_id(selection) != selection_id(changed)


def test_existing_selection_configs_validate_and_keep_pinned_ids():
    for path in selection_files():
        validate_selection(load_yaml(path), path)
    assert selection_for_dataset("run2012bc_doublemuparked", "resonance")[2] == "4d93aea9"
    assert selection_id(load_yaml("configs/selections/z_certified_2016.yaml")) == "ce293c54"


def test_unknown_selection_key_fails_with_key_and_filename(tmp_path, monkeypatch):
    _copy_configs(tmp_path, monkeypatch)
    path = tmp_path / "configs" / "selections" / "invalid.yaml"
    data = load_yaml("configs/selections/resonance_ladder_2012.yaml")
    data["muon"]["surprise_cut"] = 99
    path.write_text(__import__("yaml").safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="surprise_cut") as error:
        selection_for_dataset("run2012bc_doublemuparked", "resonance")
    assert str(path) in str(error.value)


def test_multiple_selections_require_and_resolve_analysis(tmp_path, monkeypatch):
    _copy_configs(tmp_path, monkeypatch)
    source = load_yaml("configs/selections/resonance_ladder_2012.yaml")
    source["dataset"] = "toy"
    resonance = tmp_path / "configs" / "selections" / "toy_resonance.yaml"
    reckoning = tmp_path / "configs" / "selections" / "toy_reckoning.yaml"
    resonance.write_text(
        __import__("yaml").safe_dump({**source, "analysis": "resonance"}), encoding="utf-8"
    )
    reckoning.write_text(
        __import__("yaml").safe_dump({**source, "analysis": "reckoning"}), encoding="utf-8"
    )

    assert selection_for_dataset("toy", "resonance")[1]["analysis"] == "resonance"
    assert selection_for_dataset("toy", "reckoning")[1]["analysis"] == "reckoning"
    with pytest.raises(ValueError, match="Ambiguous selections.*reckoning.*resonance"):
        selection_for_dataset("toy")


def _copy_configs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COLLIDERLAKE_ROOT", str(tmp_path))
    shutil.copytree("configs", tmp_path / "configs")


def test_fit_config_id_is_stable_and_short():
    fit_config = load_yaml("configs/fits/resonance_ladder.yaml")
    assert fit_config_id(fit_config) == fit_config_id(fit_config)
    assert len(fit_config_id(fit_config)) == 8


def test_z_fit_window_is_ordered_and_has_two_edges():
    fit_config = load_yaml("configs/fits/resonance_ladder.yaml")
    window = fit_config["fits"]["z"]["window"]
    assert len(window) == 2
    assert window[0] < window[1]
