"""F05: rolling-origin backtests with baselines, honest intervals, and a 2025 out-of-sample check."""

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
    # naive forecast from origin 2020 must be the 2020 value, whatever comes later
    assert bt[(bt["origin"] == 2020)]["forecast"].eq(30.0).all()


def test_seasonal_naive_repeats_last_year():
    y = np.array([1.0, 2, 3, 4, 5, 6, 7, 8])
    assert F.seasonal_naive(y, 6).tolist() == [5, 6, 7, 8, 5, 6]


def test_summary_reports_baselines_and_origins():
    f = json.loads((OUT / "forecast.json").read_text())
    assert {"naive", "drift", "ets_damped"} <= set(f["annual"]["mape_by_model"])
    assert {"naive", "seasonal_naive"} <= set(f["quarterly_asp"]["mape_by_model"])
    assert len(f["annual"]["origins"]) >= 5
    assert f["quarterly_asp"]["n_series"] >= 10


def test_interval_coverage_is_measured_out_of_calibration_and_in_range():
    f = json.loads((OUT / "forecast.json").read_text())
    for problem in ("annual", "quarterly_asp"):
        for row in f[problem]["pi80_coverage_eval"]:
            assert row["n_eval"] >= 50
            assert 0.65 <= row["coverage_80"] <= 0.95, (problem, row)


def test_external_2025_check_exists():
    f = json.loads((OUT / "forecast.json").read_text())
    assert f["external_2025"]["n_molecules"] >= 10
    ext = pd.read_csv(OUT / "forecast_external_2025.csv")
    assert ext["actual_2025"].gt(0).all()


def test_plan_forecasts_cover_2027():
    q = pd.read_csv(OUT / "forecasts_quarterly_asp.csv")
    assert set(q["quarter"]) == {"2027Q1", "2027Q2", "2027Q3", "2027Q4"}
    assert (q["lo80"] <= q["forecast"]).all() and (q["forecast"] <= q["hi80"]).all()
    a = pd.read_csv(OUT / "forecasts_annual_volume.csv")
    assert set(a["year"]) == {2025, 2026, 2027}
