from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def assert_valid_fit(row: Mapping[str, Any], pdg_mass: float, tol: float) -> None:
    status = str(row["status"]) == "valid"
    convergence = bool(row.get("converged", row.get("is_valid", row.get("convergence", status))))
    assert status and convergence
    mass_fit = float(row["mass_fit"])
    mass_stat_unc = float(row["mass_stat_unc"])
    signal_yield = float(row["signal_yield"])
    assert math.isfinite(mass_fit)
    assert math.isfinite(mass_stat_unc)
    assert mass_stat_unc > 0.0
    assert signal_yield > 0.0
    assert abs(mass_fit - pdg_mass) < tol
