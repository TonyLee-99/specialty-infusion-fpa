"""F14-F17: the plan engine's timing, net revenue, demand-driven volume and cost structure."""

import numpy as np
import pandas as pd
import pytest

from sifpa import engine as E
from sifpa import mechanics as M


def _drug(**kw):
    base = dict(hcpcs="X1", product_type="reference", flag_addon_8pct=False, ira_existing=False,
                asp_estimated=False, reference_hcpcs="", addon_pct=0.06)
    base.update(kw)
    return base


def test_payment_uses_asp_two_quarters_earlier_and_purchase_uses_current_asp():
    quarters = ["2026Q3", "2026Q4", "2027Q1", "2027Q2", "2027Q3", "2027Q4"]
    asp = [100, 95, 90, 85, 80, 75]  # falling price: lagged payment beats current cost
    path = pd.DataFrame({"hcpcs": "X1", "basis_quarter": quarters, "asp": asp})
    annual, q = E.plan_prices(pd.DataFrame([_drug()]), path)
    q1 = q[q["quarter"] == "2027Q1"].iloc[0]
    assert q1["pay_asp"] == 100 and q1["buy_asp"] == 90
    assert q1["payment_limit"] == pytest.approx(106)
    assert annual["pl_2027"].iloc[0] == pytest.approx(np.mean([100, 95, 90, 85]) * 1.06)
    assert annual["buy_asp_2027"].iloc[0] == pytest.approx(np.mean([90, 85, 80, 75]))


def test_biosimilar_addon_on_reference_and_ira_expiry_in_2027q4():
    quarters = ["2026Q3", "2026Q4", "2027Q1", "2027Q2", "2027Q3", "2027Q4"]
    path = pd.concat([pd.DataFrame({"hcpcs": "R", "basis_quarter": quarters, "asp": 30.0}),
                      pd.DataFrame({"hcpcs": "B", "basis_quarter": quarters, "asp": 10.0})])
    drugs = pd.DataFrame([_drug(hcpcs="R"), _drug(hcpcs="B", product_type="biosimilar", flag_addon_8pct=True,
                                                   ira_existing=True, reference_hcpcs="R")])
    _a, q = E.plan_prices(drugs, path)
    b = q[q["hcpcs"] == "B"].set_index("quarter")["payment_limit"]
    assert b["2027Q3"] == pytest.approx(10 + 0.08 * 30)
    assert b["2027Q4"] == pytest.approx(10 + 0.06 * 30)  # window for existing biosimilars ends 2027-09-30
    _a, q28 = E.plan_prices(drugs, path, rules_year=2028)
    assert q28[q28["hcpcs"] == "B"]["payment_limit"].max() == pytest.approx(10 + 0.06 * 30)


def test_every_payer_has_a_net_collection_haircut():
    d = E.Drivers.from_yaml()
    for p in E.PAYERS:
        assert 0.85 < d.collect(p) < 1.0, p
    assert d.collect("medicare_ffs") == pytest.approx(M.provider_collection_factor(d.coinsurance_collection_rate)
                                                      * (1 - d.denial_writeoff_medicare))
    hi = E.Drivers.from_yaml(commercial_patient_resp_share=0.2, patient_collection_rate=0.5)
    assert hi.collect("commercial") < d.collect("commercial")


def test_ma_rate_scales_revenue_not_margin():
    """MA at 95% of FFS must cut revenue (cost unchanged), not shrink the margin."""
    d1, d95 = E.Drivers.from_yaml(), E.Drivers.from_yaml(ma_rate_vs_ffs=0.95)
    revenue, cost = 1000.0, 980.0
    m1 = revenue * d1.collect("medicare_adv") - cost
    m95 = revenue * d95.collect("medicare_adv") - cost
    assert m1 - m95 == pytest.approx(revenue * d1.collect("medicare_adv") * 0.05)


def test_fixed_costs_do_not_depend_on_volume():
    f = E.fixed_costs(12)
    assert f["total"] == pytest.approx(f["nursing"] + f["rent_equipment"] + f["site_staff"])
    assert E.fixed_costs(13)["total"] > f["total"]


def test_pnl_reconciles_including_pharmacy_margin():
    r = E.build(rules_year=2028, white_bag=True, mfp=True)["pnl"]
    lines = r["drug_revenue"] + r["admin_revenue"] + r["pharmacy_margin"] - r["drug_cost"] - r["variable_cost"]
    assert lines == pytest.approx(r["contribution"], abs=1.0)
    assert r["pharmacy_margin"] > 0


def test_white_bag_tiers_target_expensive_drugs():
    econ = pd.DataFrame({"hcpcs": ["a", "b", "c"], "acquisition_cost": [500.0, 5000.0, 30000.0]})
    t = E.white_bag_tiers(econ)
    assert t["a"] < t["b"] < t["c"]
