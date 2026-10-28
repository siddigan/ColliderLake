from src.utils.config import fit_config_id, load_yaml, selection_id


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


def test_fit_config_id_is_stable_and_short():
    fit_config = load_yaml("configs/fits/resonance_ladder.yaml")
    assert fit_config_id(fit_config) == fit_config_id(fit_config)
    assert len(fit_config_id(fit_config)) == 8


def test_z_fit_window_matches_full_window_m1_configuration():
    fit_config = load_yaml("configs/fits/resonance_ladder.yaml")
    assert fit_config["fits"]["z"]["window"] == [70.0, 110.0]
