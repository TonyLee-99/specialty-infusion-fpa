"""Suppression-aware biosimilar intervals at code grain, structural zeros, no EB, no names."""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_enough_regional_providers_and_no_names():
    sc = pd.read_csv(ROOT / "exports/fact_provider_scorecard.csv", dtype={"npi": str})
    assert len(sc) >= 300 and sc["npi"].is_unique
    for path in ("exports/fact_provider_scorecard.csv", "exports/fact_provider_biosimilar.csv"):
        cols = pd.read_csv(ROOT / path, nrows=1).columns.str.lower()
        assert not any("name" in c or "first" in c or "last" in c for c in cols)


def test_no_exported_count_below_11():
    sc = pd.read_csv(ROOT / "exports/fact_provider_scorecard.csv")
    assert sc["benes"].min() >= 11
    bio = pd.read_csv(ROOT / "exports/fact_provider_biosimilar.csv")
    for col in ("bio_benes_visible", "ref_benes_visible"):
        assert ((bio[col] == 0) | (bio[col] >= 11)).all()


def test_structural_zeros_are_not_imputed():
    s = json.loads((ROOT / "outputs/benchmark.json").read_text())
    assert {"denosumab", "natalizumab"} <= set(s["molecules_with_no_2024_biosimilar"])
    bio = pd.read_csv(ROOT / "exports/fact_provider_biosimilar.csv")
    assert not bio["molecule"].isin(["denosumab", "natalizumab"]).any()


def test_intervals_are_ordered_and_labels_follow_the_rule():
    bio = pd.read_csv(ROOT / "exports/fact_provider_biosimilar.csv")
    assert (bio["share_lo"] <= bio["share_hi"]).all()
    above = bio[bio["vs_state"] == "above_state"]
    assert (above["share_lo"] > above["state_share"]).all()
    assert (bio.loc[bio["width"] > 0.40, "vs_state"] == "insufficient_data").all()


def test_no_empirical_bayes_claim():
    s = json.loads((ROOT / "outputs/benchmark.json").read_text())
    assert s["empirical_bayes"].startswith("not used")
