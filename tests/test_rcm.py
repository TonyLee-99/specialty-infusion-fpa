"""SYNTHETIC RCM layer is labelled everywhere, reproducible, and its KPIs are coherent."""

import json
from pathlib import Path

import pandas as pd
import pytest

from sifpa.rcm import generate, kpis

ROOT = Path(__file__).resolve().parents[1]
SYN = ROOT / "synthetic" / "rcm"


def test_every_synthetic_file_is_labelled():
    files = [p for p in (ROOT / "synthetic").rglob("*") if p.is_file()]
    assert files
    for p in files:
        assert "SYNTHETIC" in p.name or "SYNTHETIC" in p.read_text()[:400], p


def test_every_row_carries_the_label():
    for name in ("claims_837_SYNTHETIC.csv", "remits_835_SYNTHETIC.csv"):
        df = pd.read_csv(SYN / name)
        assert (df["data_label"] == "SYNTHETIC").all()


def test_generation_is_reproducible():
    claims, remits = generate.generate()
    on_disk = pd.read_csv(SYN / "claims_837_SYNTHETIC.csv")
    assert len(claims) == len(on_disk)
    assert claims["expected_allowed"].sum() == pytest.approx(on_disk["expected_allowed"].sum(), rel=1e-9)


def test_kpis_are_coherent():
    k = json.loads((ROOT / "outputs/rcm_kpis_SYNTHETIC.json").read_text())
    assert k["data_label"] == "SYNTHETIC"
    for key in ("clean_claim_rate", "denial_rate", "net_collection_rate"):
        assert 0 < k[key] < 1
    assert sum(k["denial_rate_by_carc_group"].values()) == pytest.approx(k["denial_rate"], abs=1e-5)
    assert 0 < k["days_in_ar"] < 365
    assert kpis.compute()["denial_rate"] == pytest.approx(k["denial_rate"])
