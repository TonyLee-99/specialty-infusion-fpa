"""F06: 2027 plan scenarios are driver-based, internally consistent and labelled."""

import json
from pathlib import Path

import pandas as pd
import pytest

OUT = Path(__file__).resolve().parents[1] / "outputs"


@pytest.fixture(scope="module")
def sc():
    return json.loads((OUT / "scenarios.json").read_text())


def test_three_scenarios_present(sc):
    assert set(sc["scenarios"]) == {"base", "biosimilar_push", "policy_shock"}


def test_annual_equals_volume_times_per_admin(sc):
    for s in sc["scenarios"].values():
        a, p = s["annual"], s["per_admin"]
        assert a["contribution"] == pytest.approx(a["administrations"] * p["contribution"], rel=1e-3)


def test_volume_is_capacity_driven(sc):
    v = sc["volume_drivers"]
    booked = v["chairs"] * v["operating_days"] * v["chair_hours_per_day"] * v["chair_utilization"]
    base = sc["scenarios"]["base"]
    assert base["annual"]["administrations"] == pytest.approx(booked / base["per_admin"]["chair_hours"], rel=1e-3)


def test_policy_shock_bridge_components_are_negative(sc):
    assert sc["policy_shock_bridge"]["mfp_orencia_entyvio"] < 0
    assert sc["policy_shock_bridge"]["white_bagging"] < 0


def test_push_mix_conserves_volume():
    t = pd.read_csv(OUT / "scenario_drug_inputs.csv")
    assert t["mix_base"].sum() == pytest.approx(1.0, abs=1e-5)  # CSV rounds to 6 dp
    assert t["mix_push"].sum() == pytest.approx(1.0, abs=1e-5)


def test_ira_existing_biosimilars_get_blended_2027_addon():
    t = pd.read_csv(OUT / "scenario_drug_inputs.csv")
    existing = t[t["ira_existing"] & t["flag_addon_8pct"]]
    assert len(existing) > 0
    assert existing["addon_2027"].round(4).eq(0.075).all()  # 8% for Q1-Q3, 6% for Q4
