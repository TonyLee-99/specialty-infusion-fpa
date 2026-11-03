"""Budget-vs-actual pack. Budget = plan by site/month; actuals SYNTHETIC; bridge adds up exactly."""

import json
from pathlib import Path

import pandas as pd
import pytest

from sifpa import variance as V

ROOT = Path(__file__).resolve().parents[1]


def test_budget_months_sum_to_the_annual_plan():
    b = pd.read_csv(ROOT / "exports/fact_plan_month.csv")
    sc = json.loads((ROOT / "outputs/scenarios.json").read_text())["scenarios"]["base"]
    s1 = b[b["site_id"] == "S1"]
    assert s1["month_start"].nunique() == 12
    assert s1["contribution"].sum() == pytest.approx(sc["contribution"], abs=1.0)


def test_bridge_identity_holds_at_every_grain():
    b = pd.read_csv(ROOT / "exports/fact_plan_month.csv")
    a = pd.read_csv(ROOT / "exports/fact_actual_month_SYNTHETIC.csv")
    for keys in ([], ["site_id"], ["site_id", "month_start"]):
        br = V.bridge(b, a, keys)
        assert ((br["volume"] + br["mix"] + br["rate"] - br["variance"]).abs() < 1e-6).all()


def test_actuals_are_labelled_synthetic_everywhere():
    a = pd.read_csv(ROOT / "exports/fact_actual_month_SYNTHETIC.csv")
    assert (a["data_label"] == "SYNTHETIC").all()
    assert "SYNTHETIC" in (ROOT / "docs/VARIANCE_PACK_SYNTHETIC.md").read_text()[:200]


def test_power_bi_guide_quotes_current_kpis():
    k = json.loads((ROOT / "outputs/kpis.json").read_text())
    guide = (ROOT / "docs/powerbi_build_guide.md").read_text()
    assert f"${k['budget_contribution']:,.0f}" in guide and f"${k['volume_variance_synthetic']:,.0f}" in guide
    assert "never been" in guide and "opened in Power BI Desktop" in guide
