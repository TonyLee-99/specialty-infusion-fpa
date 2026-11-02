"""F06: the Excel scenario workbook is formula-driven and agrees with the Python model."""

import json
import re
from pathlib import Path

import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "excel" / "infusion_plan_2027_scenarios.xlsx"
STRUCTURAL = {"0", "1", "1.5", "2", "3", "4"}  # rule constants: CPT add-on threshold, 3-of-4 quarters, etc.


@pytest.fixture(scope="module")
def wb():
    return load_workbook(XLSX)


def test_tabs_flow_inputs_calc_outputs(wb):
    assert {"Inputs", "PFS", "Drugs", "Calc", "Outputs", "README"} <= set(wb.sheetnames)


def test_at_least_100_live_formulas(wb):
    n = sum(1 for ws in wb.worksheets for row in ws.iter_rows() for c in row
            if isinstance(c.value, str) and c.value.startswith("="))
    assert n >= 100
    check = json.loads((ROOT / "outputs/excel_recalc_check.json").read_text())
    assert check["n_formulas"] == n  # committed recalc check belongs to this workbook


def test_calc_and_outputs_have_no_hardcoded_numbers(wb):
    for name in ("Calc", "Outputs"):
        for row in wb[name].iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value, int | float):
                    pytest.fail(f"{name}!{c.coordinate} is a typed number")
                if isinstance(c.value, str) and c.value.startswith("="):
                    # drop identifiers (cell refs, sheet names, defined names like fee_96413) first
                    bare = re.sub(r"[A-Za-z_$][A-Za-z_0-9$]*", " ", c.value)
                    literals = set(re.findall(r"\d+\.?\d*", bare))
                    assert literals <= STRUCTURAL, (name, c.coordinate, literals)


def test_libreoffice_recalculation_matches_python():
    check = json.loads((ROOT / "outputs/excel_recalc_check.json").read_text())
    assert check["libreoffice_recalc"] is True
    assert len(check["comparisons"]) == 12
    assert check["max_rel_diff"] < 0.001  # acceptance A7: within 0.1%
