"""F06: the Excel plan is formula-driven and agrees with the Python engine under default AND stressed inputs.

Live: where LibreOffice is installed (local, Docker, CI installs it) the workbook is rebuilt with stressed
inputs, recalculated headless and compared with engine.build() now. Otherwise the committed local check
(outputs/excel_recalc_check.json) is read and the test says so.
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "excel" / "infusion_plan_2027_scenarios.xlsx"
STRUCTURAL = {"0", "1", "1.5", "12"}  # CPT add-on threshold, months per year


@pytest.fixture(scope="module")
def wb():
    return load_workbook(XLSX)


def test_tabs_flow_inputs_calc_outputs(wb):
    assert {"Inputs", "PFS", "Drugs", "Calc", "Outputs", "Monthly", "README"} <= set(wb.sheetnames)


def test_at_least_100_live_formulas(wb):
    n = sum(1 for ws in wb.worksheets for row in ws.iter_rows() for c in row
            if isinstance(c.value, str) and c.value.startswith("="))
    assert n >= 100
    assert json.loads((ROOT / "outputs/excel_recalc_check.json").read_text())["n_formulas"] == n


def test_calc_outputs_monthly_have_no_hardcoded_numbers(wb):
    for name in ("Calc", "Outputs"):
        for row in wb[name].iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value, int | float):
                    pytest.fail(f"{name}!{c.coordinate} is a typed number")
                if isinstance(c.value, str) and c.value.startswith("="):
                    bare = re.sub(r"[A-Za-z_$][A-Za-z_0-9$]*", " ", c.value)  # drop refs and names
                    assert set(re.findall(r"\d+\.?\d*", bare)) <= STRUCTURAL, (name, c.coordinate)


def test_committed_recalc_check_covers_default_and_stressed_inputs():
    check = json.loads((ROOT / "outputs/excel_recalc_check.json").read_text())
    cases = {c["case"]: c for c in check["cases"]}
    assert {"default inputs", "stressed inputs"} <= set(cases)
    assert cases["stressed inputs"]["inputs"]["ma_rate_vs_ffs"] != 1.0
    assert check["max_rel_diff"] < 1e-4


@pytest.mark.skipif(not (shutil.which("soffice") or shutil.which("libreoffice")), reason="LibreOffice not installed")
def test_live_recalculation_matches_python_under_stressed_inputs():
    from sifpa import engine as E
    from sifpa import excel_workbook as X
    res = X.compare(E.connect(), X.STRESS, "stressed (live)")
    assert res["libreoffice_recalc"] and res["max_rel_diff"] < 1e-4
