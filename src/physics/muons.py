from __future__ import annotations

import math

from src.physics.pdg import MUON_MASS_GEV


def invariant_mass(
    pt1: float,
    eta1: float,
    phi1: float,
    pt2: float,
    eta2: float,
    phi2: float,
    mass1: float = MUON_MASS_GEV,
    mass2: float = MUON_MASS_GEV,
) -> float:
    e1 = math.sqrt((pt1 * math.cosh(eta1)) ** 2 + mass1**2)
    e2 = math.sqrt((pt2 * math.cosh(eta2)) ** 2 + mass2**2)
    px = pt1 * math.cos(phi1) + pt2 * math.cos(phi2)
    py = pt1 * math.sin(phi1) + pt2 * math.sin(phi2)
    pz = pt1 * math.sinh(eta1) + pt2 * math.sinh(eta2)
    mass2_value = (e1 + e2) ** 2 - px**2 - py**2 - pz**2
    return math.sqrt(max(mass2_value, 0.0))


def four_vector(pt: float, eta: float, phi: float, mass: float = MUON_MASS_GEV) -> dict[str, float]:
    return {
        "energy": math.sqrt((pt * math.cosh(eta)) ** 2 + mass**2),
        "px": pt * math.cos(phi),
        "py": pt * math.sin(phi),
        "pz": pt * math.sinh(eta),
    }


def pair_kinematics(
    pt1: float,
    eta1: float,
    phi1: float,
    pt2: float,
    eta2: float,
    phi2: float,
    mass1: float = MUON_MASS_GEV,
    mass2: float = MUON_MASS_GEV,
) -> dict[str, float]:
    first = four_vector(pt1, eta1, phi1, mass1)
    second = four_vector(pt2, eta2, phi2, mass2)
    energy = first["energy"] + second["energy"]
    px = first["px"] + second["px"]
    py = first["py"] + second["py"]
    pz = first["pz"] + second["pz"]
    mass2_value = energy**2 - px**2 - py**2 - pz**2
    denominator = energy - pz
    rapidity = 0.0 if denominator <= 0.0 else 0.5 * math.log((energy + pz) / denominator)
    return {
        "mass": math.sqrt(max(mass2_value, 0.0)),
        "pt_pair": math.sqrt(px**2 + py**2),
        "rapidity": rapidity,
    }


def delta_phi(phi1: float, phi2: float) -> float:
    raw = abs(phi1 - phi2)
    return (2.0 * math.pi - raw) if raw > math.pi else raw


def delta_r(eta1: float, phi1: float, eta2: float, phi2: float) -> float:
    return math.sqrt((eta1 - eta2) ** 2 + delta_phi(phi1, phi2) ** 2)
