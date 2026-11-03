"""CI regenerates the price path, per-infusion economics and the suite P&L from the committed
fixture warehouse (built by `make dbt-ci`) and compares them with the committed outputs, so code changes
whose outputs were not regenerated fail the gate.

The price path and per-drug economics use only ASP files, PFS and national utilization, which the fixture
slice contains in full, so they must equal outputs/*.csv exactly. The suite P&L also depends on the
provider mix (Ohio-only in the fixture), so it is compared with tests/fixtures/expected_regen.json.
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
CI_WH = ROOT / "tests/fixtures/ci_warehouse.duckdb"
pytestmark = pytest.mark.skipif(not CI_WH.exists(), reason="run `make dbt-ci` first (make check does)")


@pytest.fixture(scope="module")
def ci_con():
    os.environ["SIFPA_WAREHOUSE"] = str(CI_WH)
    from sifpa import engine as E
    yield E.connect()
    os.environ.pop("SIFPA_WAREHOUSE", None)


def test_price_path_regenerates_exactly(ci_con):
    from sifpa import forecast as F
    _bt, path, _s = F.run_quarterly(ci_con)
    committed = pd.read_csv(ROOT / "outputs/price_path.csv", dtype={"hcpcs": str})
    m = committed.merge(path, on=["hcpcs", "basis_quarter"], suffixes=("_c", "_n"))
    assert len(m) == len(committed)
    assert np.allclose(m["asp_c"], m["asp_n"], rtol=1e-6)


def test_per_infusion_economics_regenerate_exactly(ci_con):
    from sifpa import assumptions as A
    from sifpa import engine as E
    drugs = E.drug_frame(ci_con)
    annual, _q = E.plan_prices(drugs, E.load_price_path())
    econ = E.per_admin(drugs, annual, E.admin_fee_table(ci_con, A.value("policy", "cf_2027_proposed")),
                       E.Drivers.from_yaml())
    committed = pd.read_csv(ROOT / "outputs/margin_per_admin.csv", dtype={"hcpcs": str})
    m = committed.merge(econ, on="hcpcs", suffixes=("_c", "_n"))
    assert len(m) == len(committed)
    for col in ("pl_2027", "acquisition_cost", "contribution_medicare_ffs", "contribution_commercial"):
        assert np.allclose(m[f"{col}_c"], m[f"{col}_n"], rtol=1e-6, atol=1e-3), col


def test_suite_pnl_matches_fixture_expectation(ci_con):
    from sifpa import engine as E
    r = E.build(ci_con)
    exp = json.loads((ROOT / "tests/fixtures/expected_regen.json").read_text())
    for k, v in exp.items():
        assert r["pnl"][k] == pytest.approx(v, rel=1e-6), k
