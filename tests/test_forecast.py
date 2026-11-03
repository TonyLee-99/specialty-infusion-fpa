"""Validation-selected models scored on an untouched test window, DM tests, decision rule,
conformal coverage measured out of sample, volume and spend scored separately."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from sifpa import forecast as F

OUT = Path(__file__).resolve().parents[1] / "outputs"


def test_backtest_uses_only_past_data():
    s = pd.Series([10.0, 11, 12, 30, 14, 15, 16, 17], index=range(2017, 2025))
    bt = F.backtest(s, {"naive": F.naive}, horizons=2, first_origin=3, season=1)
    assert (bt["target"] > bt["origin"]).all()
    assert bt[(bt["origin"] == 2020)]["forecast"].eq(30.0).all()


def test_dm_test_detects_a_clearly_better_model():
    rng = np.random.default_rng(1)
    base = rng.normal(0, 1, 200)
    r = F.dm_test(base * 0.5, base, h=1)
    assert r["dm"] < 0 and r["p_value"] < 0.01


def test_windows_are_disjoint_and_the_decision_never_uses_the_test_window():
    f = json.loads((OUT / "forecast.json").read_text())
    q = f["quarterly_asp"]
    assert q["selection_last_target"] < q["decision_last_target"] < q["test_first_origin"]
    assert "decision window" in q["decision"]
    assert q["dm_per_series_h1"]["n_series_tested"] > 0  # per-series DM, not a pooled stack
    for metric in ("administrations", "allowed"):
        assert "decision window" in f["annual"][metric]["decision"]


def test_selected_vs_naive_is_compared_on_matched_forecasts():
    a = pd.DataFrame({"series": ["a", "a", "b"], "origin": [1, 2, 1], "h": [1, 1, 1], "ape": [0.1, 0.2, 0.3]})
    b = pd.DataFrame({"series": ["a", "b", "c"], "origin": [1, 1, 1], "h": [1, 1, 1], "ape": [0.0, 0.0, 0.0]})
    x, y = F._matched(a, b)
    assert len(x) == len(y) == 2 and set(x["series"]) == {"a", "b"}


def test_interval_coverage_is_reported_per_horizon():
    f = json.loads((OUT / "forecast.json").read_text())
    cov = f["quarterly_asp"]["pi80_test_coverage_by_h"]
    assert set(cov) == {str(h) for h in range(1, 7)}
    assert 0.70 <= f["quarterly_asp"]["pi80_test_coverage_overall"] <= 0.90  # honest band around 80%


def test_price_path_covers_the_plan_horizon_and_flags_held_codes():
    p = pd.read_csv(OUT / "price_path.csv")
    assert p.groupby("hcpcs")["h"].max().eq(6).all()
    held = p[p["model"] == "held"]
    assert held["guard"].str.startswith("held_").all()


def test_chair_and_injection_volume_reported_apart():
    f = json.loads((OUT / "forecast.json").read_text())
    assert set(f["national_inoffice_admins_2024"]) == {"chair", "injection"}
