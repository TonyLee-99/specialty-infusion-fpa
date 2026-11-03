"""2027 per-infusion economics, underwater definitions, biosimilar decision table, tornado."""

import json
from pathlib import Path

import pandas as pd
import pytest

from sifpa import assumptions as A
from sifpa import engine as E

OUT = Path(__file__).resolve().parents[1] / "outputs"


@pytest.fixture(scope="module")
def econ():
    return pd.read_csv(OUT / "margin_per_admin.csv", dtype={"hcpcs": str})


def test_at_least_15_drugs_priced(econ):
    assert econ["hcpcs"].nunique() >= 15


def test_medicare_margin_recomputes_with_lag_and_net_collection(econ):
    d = E.Drivers.from_yaml()
    prem = econ["flag_lesser_of"].map({True: d.lesser_of_acquisition_premium, False: 0.0})
    acq = econ["units_per_admin"] * econ["buy_asp_2027"] * (1 + d.acquisition_spread_vs_asp + prem)
    expected = econ["units_per_admin"] * econ["pl_2027"] * d.collect("medicare_ffs") - acq
    assert (expected - econ["drug_margin_medicare_ffs"]).abs().max() < 0.10  # CSV rounds inputs to 4 dp


def test_underwater_definitions_are_nested():
    u = json.loads((OUT / "margin.json").read_text())["underwater"]
    raw, seq, both = (u[k]["share_drug_quarters"] for k in ("raw", "after_sequestration", "after_sequestration_and_coinsurance"))
    assert raw <= seq <= both
    assert u["after_sequestration_and_coinsurance"]["dollar_weighted_share"] is not None


def test_insufficient_history_picks_are_never_robust():
    dec = pd.read_csv(OUT / "biosimilar_decision.csv")
    best = dec[dec["best_for_payer"]]
    assert not (best["decision_robust"] & best["insufficient_price_history"]).any()


def test_biosimilar_decision_table_is_product_by_payer():
    dec = pd.read_csv(OUT / "biosimilar_decision.csv")
    assert set(dec["payer"]) == set(E.PAYERS)
    one_best = dec.groupby(["molecule", "payer"])["best_for_payer"].sum()
    assert (one_best == 1).all()
    assert {"decision_robust", "insufficient_price_history"} <= set(dec.columns)


def test_tornado_covers_every_ranged_practice_assumption():
    t = json.loads((OUT / "tornado.json").read_text())
    drivers = {b["driver"] for b in t["bars"]}
    assert {k for s, k, *_ in A.ranged() if s == "practice"} <= drivers
    swings = [b["swing"] for b in t["bars"]]
    assert swings == sorted(swings, reverse=True)
    assert "lesser_of_acquisition_premium" in drivers


def test_lag_spread_uses_only_known_current_asp():
    lag = pd.read_csv(OUT / "lag_spread_by_drug.csv")
    assert lag["quarters"].max() <= 38
