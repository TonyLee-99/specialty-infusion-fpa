"""F06/F15-F19: 2027 plan scenarios are demand-driven, labelled and internally consistent."""

import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


@pytest.fixture(scope="module")
def sc():
    return json.loads((OUT / "scenarios.json").read_text())


def test_scenarios_present(sc):
    assert {"base", "biosimilar_listed", "biosimilar_best", "policy_2028", "base_full_formulary",
            "policy_2028_full_formulary"} <= set(sc["scenarios"])


def test_operating_margin_is_contribution_minus_fixed(sc):
    for s in sc["scenarios"].values():
        assert s["operating_margin"] == pytest.approx(s["contribution"] - s["fixed_costs"]["total"], abs=2)


def test_volume_is_demand_driven_and_capacity_is_a_check(sc):
    b = sc["scenarios"]["base"]
    assert b["patients"] > 0 and 0 < b["utilization"] <= 1
    assert b["added_chair_value"] < 0  # demand below capacity: an extra chair only adds fixed cost
    assert sc["value_of_100_more_patients"] > 0


def test_breakeven_markup_zeroes_operating_margin(sc):
    assert 0 < sc["breakeven_commercial_markup"] < 0.20
    assert abs(sc["breakeven_check_operating_margin"]) < 1.0


def test_lag_drift_scenario_and_growth_labels(sc):
    assert sc["lag_drift_scenario"]["n_drugs_with_history"] >= 10
    assert "linear" in sc["growth_labels"]["value_of_100_more_patients"]
    assert "fixed cost" in sc["growth_labels"]["added_chair_value"]


def test_policy_2028_bridge_and_labels(sc):
    br = sc["policy_2028_bridge"]
    assert br["white_bagging_net_of_ivs"] < 0 and br["ira_addon_expiry"] <= 0
    assert "2027 prices held" in sc["labels"]["policy_2028"]
    ivs = sc["policy_2028_operating_margin_by_ivs_recapture"]
    assert ivs["0.0"] < ivs["0.25"] < ivs["0.5"]


def test_mix_is_formulary_listed_and_payer_specific():
    mix = pd.read_csv(OUT / "scenario_mix.csv", dtype={"hcpcs": str})
    drugs = pd.read_csv(ROOT / "dbt/seeds/drug_catalog.csv", dtype=str).set_index("hcpcs")
    assert (drugs.loc[mix["hcpcs"], "formulary_listed"] == "Y").all()
    for _payer, g in mix.groupby("payer"):
        assert g["share_base"].sum() == pytest.approx(1.0, abs=1e-6)
    neuro = mix[mix["line"] == "neuro"].groupby("payer")["share_base"].sum()
    assert neuro["commercial"] > neuro["medicare_ffs"]  # MS skews to working-age commercial patients


def test_biosimilar_push_lands_on_listed_products():
    mix = pd.read_csv(OUT / "scenario_mix.csv", dtype={"hcpcs": str})
    moved = mix[mix["share_listed"] > mix["share_base"] + 1e-9]["hcpcs"].unique()
    assert set(moved) <= {"Q5103", "Q5115"}
