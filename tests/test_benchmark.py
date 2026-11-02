"""F07: provider benchmarking is suppression-aware, shrunk, interval-based and anonymous."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sifpa import benchmark as B

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sc():
    return pd.read_csv(ROOT / "exports/fact_provider_scorecard.csv", dtype={"npi": str, "county_fips": str})


def test_enough_regional_providers(sc):
    assert len(sc) >= 300
    assert sc["npi"].is_unique


def test_no_names_exported(sc):
    for path in ("exports/fact_provider_scorecard.csv", "exports/fact_provider_biosimilar.csv"):
        cols = pd.read_csv(ROOT / path, nrows=1).columns.str.lower()
        assert not any("name" in c or "first" in c or "last" in c for c in cols)


def test_no_exported_count_below_11(sc):
    assert sc["benes"].min() >= 11
    bio = pd.read_csv(ROOT / "exports/fact_provider_biosimilar.csv")
    for col in ("bio_benes", "ref_benes"):
        assert ((bio[col] == 0) | (bio[col] >= 11)).all()


def test_percentiles_are_within_specialty(sc):
    for _, g in sc.groupby("provider_type"):
        assert g["allowed_per_bene_pctile"].max() == pytest.approx(1.0)


def test_shrinkage_pulls_toward_prior():
    a, b = 2.0, 8.0  # prior mean 0.2
    post, lo, hi = B.shrink(np.array([12.0]), np.array([12.0]), a, b)
    assert 0.2 < post[0] < 1.0 and lo[0] < post[0] < hi[0]


def test_beta_prior_recovers_mean():
    rng = np.random.default_rng(0)
    n = rng.integers(11, 200, 400).astype(float)
    x = rng.binomial(n.astype(int), 0.3).astype(float)
    a, b = B.beta_prior(x, n)
    assert a / (a + b) == pytest.approx(0.3, abs=0.02)


def test_above_peer_requires_interval_to_clear_median(sc):
    above = sc[sc["biosimilar_vs_peer"] == "above_peer"]
    med = sc.groupby("provider_type")["biosimilar_rate_shrunk"].median()
    assert (above["biosimilar_ci_lo"] > above["provider_type"].map(med)).all()


def test_summary_reports_censoring_and_market_view():
    s = json.loads((ROOT / "outputs/benchmark.json").read_text())
    assert 0 <= s["share_provider_molecule_censored"] <= 1
    assert "US" in s["market_biosimilar_share_2024"]["infliximab"]
