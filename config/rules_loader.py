"""
config/rules_loader.py

Purpose : Load config/rules.yaml into a typed Rules object.
Inputs  : config/rules.yaml
Outputs : RULES — module-level singleton, loaded once at import time.

Domain experts edit rules.yaml; this module makes those values available to
all processing code without requiring any Python knowledge.
"""
from __future__ import annotations

from pathlib import Path
from typing import Final

import yaml

_RULES_PATH: Final[Path] = Path(__file__).parent / "rules.yaml"


class Rules:
    """Typed container for all drought classification rules and thresholds."""

    def __init__(self, raw: dict) -> None:
        dq = raw["data_quality"]
        self.staleness_days: int = int(dq["staleness_days"])
        self.coverage_error_threshold: float = float(dq["coverage_error_threshold"])
        self.outlier_iqr_factor: float = float(dq["outlier_iqr_factor"])
        self.indicator_columns: list[str] = list(dq["indicator_columns"])

        cdi = raw["cdi"]
        self.cdi_critical_min: int = int(cdi["critical_min"])
        self.cdi_dry_min: int = int(cdi["dry_min"])

        ind = raw["indicator_deficits"]
        self.precip_1m_index_min: int = int(ind["precip_1m_index_min"])
        self.soil_moisture_index_min: int = int(ind["soil_moisture_index_min"])

        hist = raw["historic"]
        self.window_weeks: int = int(hist["window_weeks"])

        fc = raw["forecast"]
        self.horizon_days: int = int(fc["horizon_days"])
        self.max_delta_days: int = int(fc["max_delta_days"])

        wl = raw["warnlevel"]
        self.fallback_min: int = int(wl["fallback_min"])

        vhi = raw["vhi"]
        self.vhi_stress_index_min: int = int(vhi["stress_index_min"])
        self.vhi_thresholds: dict[int, float] = {
            int(k): float(v) for k, v in vhi["thresholds"].items()
        }


def load_rules() -> Rules:
    """Load and parse config/rules.yaml. Raises KeyError on missing keys."""
    with _RULES_PATH.open(encoding="utf-8") as f:
        return Rules(yaml.safe_load(f))


RULES: Final[Rules] = load_rules()
