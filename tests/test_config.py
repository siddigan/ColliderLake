from src.utils.config import load_yaml, selection_id


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
