import math

from src.physics.muons import invariant_mass, pair_kinematics
from src.physics.pdg import MUON_MASS_GEV


def test_invariant_mass_known_back_to_back_pair():
    mass = invariant_mass(10.0, 0.0, 0.0, 10.0, 0.0, math.pi)
    expected = 2.0 * math.sqrt(100.0 + MUON_MASS_GEV**2)
    assert abs(mass - expected) < 1e-6


def test_symmetric_pair_has_zero_rapidity_and_pair_pt():
    pair = pair_kinematics(10.0, 1.0, 0.0, 10.0, -1.0, math.pi)
    assert abs(pair["rapidity"]) < 1e-6
    assert abs(pair["pt_pair"]) < 1e-6


def test_forward_pair_has_positive_rapidity():
    pair = pair_kinematics(10.0, 1.0, 0.0, 10.0, 1.0, math.pi)
    assert pair["rapidity"] > 0.0
