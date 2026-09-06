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


def delta_phi(phi1: float, phi2: float) -> float:
    raw = abs(phi1 - phi2)
    return (2.0 * math.pi - raw) if raw > math.pi else raw


def delta_r(eta1: float, phi1: float, eta2: float, phi2: float) -> float:
    return math.sqrt((eta1 - eta2) ** 2 + delta_phi(phi1, phi2) ** 2)
