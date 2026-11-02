"""Load config/assumptions.yaml and expose values plus the tornado ranges."""

from __future__ import annotations

from functools import lru_cache

import yaml

from sifpa.paths import CONFIG


@lru_cache(maxsize=1)
def load() -> dict:
    return yaml.safe_load((CONFIG / "assumptions.yaml").read_text())


def value(section: str, key: str):
    return load()[section][key]["value"]


def practice() -> dict[str, float]:
    return {k: v["value"] for k, v in load()["practice"].items()}


def ranged() -> list[tuple[str, str, float, float, float]]:
    """Every assumption with a low/high range: (section, key, base, low, high)."""
    out = []
    for section in ("policy", "practice"):
        for key, spec in load()[section].items():
            if isinstance(spec, dict) and "low" in spec and "high" in spec:
                out.append((section, key, spec["value"], spec["low"], spec["high"]))
    return out


def infusion_time(molecule: str) -> dict:
    return load()["infusion_time"][molecule]
