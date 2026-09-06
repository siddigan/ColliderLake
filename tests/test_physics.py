from src.physics.muons import invariant_mass


def test_invariant_mass_known_back_to_back_pair():
    mass = invariant_mass(10.0, 0.0, 0.0, 10.0, 0.0, 3.141592653589793)
    assert abs(mass - 20.001116230949454) < 1e-6
