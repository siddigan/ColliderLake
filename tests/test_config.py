from src.utils.config import load_yaml, selection_id


def test_selection_id_is_stable():
    selection = load_yaml("configs/selections/resonance_ladder_2012.yaml")
    assert selection_id(selection) == selection_id(selection)
    assert len(selection_id(selection)) == 8
