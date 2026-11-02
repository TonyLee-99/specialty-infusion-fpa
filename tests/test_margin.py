"""F04: infusion margin outputs are complete, internally consistent and cover every ranged assumption."""

import json
from pathlib import Path

import pandas as pd
import pytest

from sifpa import assumptions as A
from sifpa import mechanics as M

OUT = Path(__file__).resolve().parents[1] / "outputs"


@pytest.fixture(scope="module")
def econ():
    return pd.read_csv(OUT / "margin_per_admin.csv", dtype={"hcpcs": str})


def test_at_least_15_drugs_priced(econ):
    assert econ["hcpcs"].nunique() >= 15


def test_medicare_drug_margin_recomputes_from_published_inputs(econ):
    c = M.provider_collection_factor(A.practice()["coinsurance_collection_rate"])
    s = A.practice()["acquisition_spread_vs_asp"]
    expected = econ["units_per_admin"] * (econ["payment_limit"] * c - econ["asp_basis"] * (1 + s))
    # CSV rounds inputs to 4 dp; x ~500 units that is up to ~$0.05 per administration
    assert (expected - econ["drug_margin_medicare_ffs"]).abs().max() < 0.10


def test_admin_fee_matches_family(econ):
    m = json.loads((OUT / "margin.json").read_text())
    mab = econ[(econ["admin_family"] == "mab_infusion") & (econ["admin_hours"] <= 1.5)]
    assert (mab["admin_allowed_medicare"] - m["ohio_admin_fee_96413"]).abs().max() < 0.01


def test_tornado_covers_every_ranged_practice_assumption():
    t = json.loads((OUT / "tornado.json").read_text())
    drivers = {b["driver"] for b in t["bars"]}
    ranged = {k for s, k, *_ in A.ranged() if s == "practice"}
    assert ranged <= drivers
    swings = [b["swing"] for b in t["bars"]]
    assert swings == sorted(swings, reverse=True)


def test_biosimilar_conversion_has_switch_and_expiry_economics():
    conv = json.loads((OUT / "biosimilar_conversion.json").read_text())
    for mol in ("infliximab", "rituximab", "tocilizumab"):
        assert {"switch_delta_medicare_per_admin", "switch_delta_commercial_per_admin",
                "ira_addon_expiry_hit_per_admin", "products"} <= set(conv[mol])
    assert len(conv["_infliximab_history"]) >= 100  # 4 products x ~25-40 quarters


def test_lag_spread_uses_only_known_current_asp():
    lag = pd.read_csv(OUT / "lag_spread_by_drug.csv")
    assert lag["quarters"].max() <= 38  # 40 quarters minus the 2 whose current ASP is not yet published


def test_summary_is_consistent():
    m = json.loads((OUT / "margin.json").read_text())
    b = m["blended_per_admin"]
    assert b["contribution"] == pytest.approx(b["drug_margin"] + b["admin_revenue"] - b["chair_cost"], abs=0.05)
    assert 0.9 < m["realization"]["allowed_weighted_ratio_2024"] <= 1.0
