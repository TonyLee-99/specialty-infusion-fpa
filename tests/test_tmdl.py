"""PBIP/TMDL structure, measure-to-SQL mapping, and independent pandas checks of the SQL twins.
The DAX itself has never been executed (no Power BI Desktop on this Mac)."""

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from sifpa import kpis
from sifpa.pbi_measures import MEASURES, slug

ROOT = Path(__file__).resolve().parents[1]
PBI = ROOT / "powerbi"
DEF = PBI / "SpecialtyInfusionFPA.SemanticModel" / "definition"
OUT, EXP = ROOT / "outputs", ROOT / "exports"
NAME = r"(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))"


def parse_tables() -> dict:
    tables = {}
    for path in sorted((DEF / "tables").glob("*.tmdl")):
        text = path.read_text()
        assert not any(line.startswith(" ") for line in text.splitlines()), f"{path.name}: tabs only"
        m = re.search(rf"^table {NAME}", text, re.M)
        t = m.group(1) or m.group(2)
        assert t == path.stem
        cols = [x.group(1) or x.group(2) for x in re.finditer(rf"^\tcolumn {NAME}", text, re.M)]
        measures, lines = {}, text.splitlines()
        for i, line in enumerate(lines):
            mm = re.match(rf"^\tmeasure {NAME} = (.+)$", line)
            if not mm:
                continue
            props = [n.strip() for n in lines[i + 1:i + 6] if n.startswith("\t\t")]
            measures[mm.group(1) or mm.group(2)] = {
                "dax": mm.group(3), "description": lines[i - 1].strip().lstrip("/ "),
                "folder": next((p.split(": ", 1)[1] for p in props if p.startswith("displayFolder:")), ""),
                "format": next((p.split(": ", 1)[1] for p in props if p.startswith("formatString:")), "")}
        tables[t] = {"columns": cols, "measures": measures, "partition": "partition" in text}
    return tables


@pytest.fixture(scope="module")
def tables():
    return parse_tables()


def all_measures(tables):
    return {m: spec for body in tables.values() for m, spec in body["measures"].items()}


def test_project_files_point_at_each_other():
    pbip = json.loads((PBI / "SpecialtyInfusionFPA.pbip").read_text())
    assert pbip["artifacts"][0]["report"]["path"] == "SpecialtyInfusionFPA.Report"
    pbir = json.loads((PBI / "SpecialtyInfusionFPA.Report/definition.pbir").read_text())
    assert pbir["datasetReference"]["byPath"]["path"] == "../SpecialtyInfusionFPA.SemanticModel"


def test_every_table_is_in_the_model_with_columns_matching_exports(tables):
    model = (DEF / "model.tmdl").read_text()
    for t, body in tables.items():
        assert re.search(rf"^ref table '?{re.escape(t)}'?$", model, re.M), t
        assert body["partition"]
        assert body["columns"] == pd.read_csv(EXP / f"{t}.csv", nrows=0).columns.tolist(), t


def test_relationships_reference_existing_columns(tables):
    rel = (DEF / "relationships.tmdl").read_text()
    pairs = re.findall(rf"(fromColumn|toColumn): {NAME}\.{NAME}", rel)
    assert len(pairs) >= 40
    for _k, t1, t2, c1, c2 in pairs:
        assert (c1 or c2) in tables[t1 or t2]["columns"]


def test_measures_documented_sliceable_and_resolve(tables):
    ms = all_measures(tables)
    assert len(ms) >= 20
    sliceable = [m for m in ms if m.startswith(("Budget", "Volume", "Mix", "Rate", "Contribution Variance", "Actual"))]
    assert len(sliceable) >= 8  # budget / variance measures over site x payer x drug x month
    for name, spec in ms.items():
        assert spec["description"] and spec["folder"] and spec["format"], name
        assert "SQL twin context" in spec["description"], name
        for t1, t2, col in re.findall(rf"{NAME}\[([^\]]+)\]", spec["dax"]):
            if (t1 or t2) in ("VAR", "RETURN"):
                continue
            assert col in tables[t1 or t2]["columns"], (name, t1 or t2, col)
        for ref in re.findall(r"(?<![\w'\]])\[([^\]]+)\]", spec["dax"]):
            assert ref in ms, (name, ref)


def test_every_measure_has_a_sql_twin_reproducing_the_published_value():
    published = json.loads((OUT / "kpis.json").read_text())
    fresh = kpis.compute()
    assert {slug(m[1]) for m in MEASURES} == set(published) == set(fresh)
    for k, v in fresh.items():
        assert abs(v - published[k]) < 1e-6, k


def test_sql_twins_agree_with_independent_pandas_and_analysis_outputs():
    """Non-circular checks: the SQL is compared with pandas / the analysis modules, not with itself."""
    from sifpa import variance as V
    k = json.loads((OUT / "kpis.json").read_text())
    b = pd.read_csv(EXP / "fact_plan_month.csv")
    a = pd.read_csv(EXP / "fact_actual_month_SYNTHETIC.csv")
    br = V.bridge(b, a, ["site_id"]).set_index("site_id").loc["S1"]
    for m, col in (("volume_variance_synthetic", "volume"), ("mix_variance_synthetic", "mix"),
                   ("rate_variance_synthetic", "rate"), ("contribution_variance_synthetic", "variance")):
        assert k[m] == pytest.approx(br[col], rel=1e-9, abs=1e-6), m
    assert br["volume"] + br["mix"] + br["rate"] == pytest.approx(br["variance"], abs=1e-6)
    sc = json.loads((OUT / "scenarios.json").read_text())["scenarios"]
    assert k["budget_contribution"] == pytest.approx(sc["base"]["contribution"], abs=1.0)
    assert k["scenario_contribution"] == sc["policy_2028"]["contribution"]
    bm = json.loads((OUT / "benchmark.json").read_text())
    assert k["providers_scored"] == bm["n_providers_scored"]
    assert round(k["biosimilar_share_of_administrations"], 4) == bm["market_biosimilar_share_2024"]["infliximab"]["US"]
    mk = json.loads((OUT / "market.json").read_text())
    assert k["eligible_markets"] == mk["markets"]["n_eligible"]


def test_synthetic_tables_are_labelled_in_the_model(tables):
    for t in tables:
        if "rcm" in t or "actual" in t:
            assert t.endswith("SYNTHETIC")
            assert (DEF / "tables" / f"{t}.tmdl").read_text().startswith("/// SYNTHETIC")
