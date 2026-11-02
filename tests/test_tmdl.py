"""F10: PBIP/TMDL semantic model is structurally valid and every DAX measure has a SQL twin whose DuckDB
result equals the published KPI and agrees with the analysis outputs. (Not opened in Power BI Desktop.)"""

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from sifpa import kpis
from sifpa.pbi_measures import slug

ROOT = Path(__file__).resolve().parents[1]
PBI = ROOT / "powerbi"
DEF = PBI / "SpecialtyInfusionFPA.SemanticModel" / "definition"
OUT = ROOT / "outputs"
NAME = r"(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))"


def _name(m, i=1):
    return m.group(i) or m.group(i + 1)


def parse_tables() -> dict:
    """Minimal TMDL reader: table -> {columns, measures{name: {description, folder, format, dax}}, partition}."""
    tables = {}
    for path in sorted((DEF / "tables").glob("*.tmdl")):
        text = path.read_text()
        for line in text.splitlines():
            assert not line.startswith(" "), f"{path.name}: TMDL indentation must be tabs"
        t = _name(re.search(rf"^table {NAME}", text, re.M))
        assert t == path.stem, path
        cols = [_name(m) for m in re.finditer(rf"^\tcolumn {NAME}", text, re.M)]
        measures = {}
        lines = text.splitlines()
        for i, line in enumerate(lines):
            m = re.match(rf"^\tmeasure {NAME} = (.+)$", line)
            if not m:
                continue
            props = []
            for nxt in lines[i + 1:]:
                if not nxt.startswith("\t\t"):
                    break
                props.append(nxt.strip())
            measures[_name(m)] = {
                "dax": m.group(3),
                "description": lines[i - 1].strip()[4:] if lines[i - 1].strip().startswith("///") else "",
                "folder": next((p.split(": ", 1)[1] for p in props if p.startswith("displayFolder:")), ""),
                "format": next((p.split(": ", 1)[1] for p in props if p.startswith("formatString:")), ""),
            }
        tables[t] = {"columns": cols, "measures": measures, "partition": "partition" in text}
    return tables


@pytest.fixture(scope="module")
def tables():
    return parse_tables()


def all_measures(tables):
    return {m: (t, spec) for t, body in tables.items() for m, spec in body["measures"].items()}


def test_project_files_parse_and_point_at_each_other():
    pbip = json.loads((PBI / "SpecialtyInfusionFPA.pbip").read_text())
    assert pbip["artifacts"][0]["report"]["path"] == "SpecialtyInfusionFPA.Report"
    pbir = json.loads((PBI / "SpecialtyInfusionFPA.Report/definition.pbir").read_text())
    assert pbir["datasetReference"]["byPath"]["path"] == "../SpecialtyInfusionFPA.SemanticModel"
    assert "compatibilityLevel" in (DEF / "database.tmdl").read_text()


def test_model_references_every_table_and_each_has_a_partition_over_exports(tables):
    model = (DEF / "model.tmdl").read_text()
    for t, body in tables.items():
        assert re.search(rf"^ref table '?{re.escape(t)}'?$", model, re.M), t
        assert body["partition"], t
        assert (ROOT / "exports" / f"{t}.csv").exists(), t


def test_columns_match_export_headers(tables):
    for t, body in tables.items():
        header = pd.read_csv(ROOT / "exports" / f"{t}.csv", nrows=0).columns.tolist()
        assert body["columns"] == header, t


def test_date_table_is_marked(tables):
    text = (DEF / "tables" / "dim_date.tmdl").read_text()
    assert "dataCategory: Time" in text and "isKey" in text


def test_relationships_reference_existing_columns(tables):
    rel = (DEF / "relationships.tmdl").read_text()
    pairs = re.findall(rf"(fromColumn|toColumn): {NAME}\.{NAME}", rel)
    assert len(pairs) >= 20
    for _kind, t1, t2, c1, c2 in pairs:
        t, c = t1 or t2, c1 or c2
        assert c in tables[t]["columns"], f"{t}.{c}"


def test_at_least_15_measures_each_documented_and_foldered(tables):
    ms = all_measures(tables)
    assert len(ms) >= 15
    for name, (_t, spec) in ms.items():
        assert spec["description"], name
        assert spec["folder"], name
        assert spec["format"], name


def test_dax_references_resolve(tables):
    ms = all_measures(tables)
    for name, (_t, spec) in ms.items():
        for t1, t2, col in re.findall(rf"{NAME}\[([^\]]+)\]", spec["dax"]):
            t = t1 or t2
            if t in ("VAR", "RETURN"):
                continue
            assert t in tables, (name, t)
            assert col in tables[t]["columns"], (name, t, col)
        for ref in re.findall(r"(?<![\w'\]])\[([^\]]+)\]", spec["dax"]):
            assert ref in ms, (name, ref)


def test_every_measure_has_a_sql_twin_and_published_value(tables):
    published = json.loads((OUT / "kpis.json").read_text())
    for name in all_measures(tables):
        s = slug(name)
        assert (ROOT / "sql" / "measures" / f"{s}.sql").exists(), name
        assert s in published, name


def test_sql_twins_reproduce_published_values():
    published = json.loads((OUT / "kpis.json").read_text())
    fresh = kpis.compute()
    assert set(fresh) == set(published)
    for k, v in fresh.items():
        assert abs(v - published[k]) < 1e-6, k


def test_sql_twins_agree_with_analysis_outputs():
    k = json.loads((OUT / "kpis.json").read_text())
    sc = json.loads((OUT / "scenarios.json").read_text())["scenarios"]
    assert k["base_annual_contribution"] == sc["base"]["annual"]["contribution"]
    assert k["policy_shock_delta"] == sc["policy_shock"]["annual"]["contribution"] - sc["base"]["annual"]["contribution"]
    b = json.loads((OUT / "benchmark.json").read_text())
    assert k["providers_scored"] == b["n_providers_scored"]
    assert round(k["infliximab_biosimilar_share_2024"], 4) == b["market_biosimilar_share_2024"]["infliximab"]["US"]
    m = json.loads((OUT / "margin.json").read_text())
    assert k["medicare_contribution_per_admin"] == pytest.approx(m["medicare_ffs_per_admin"]["contribution"], abs=0.01)
    assert k["commercial_contribution_per_admin"] == pytest.approx(m["commercial_per_admin"]["contribution"], abs=0.01)
    mk = json.loads((OUT / "market.json").read_text())
    assert k["eligible_markets"] == mk["markets"]["n_eligible"]


def test_synthetic_tables_are_labelled_in_the_model(tables):
    for t in tables:
        if "rcm" in t:
            assert t.endswith("SYNTHETIC")
            assert (DEF / "tables" / f"{t}.tmdl").read_text().startswith("/// SYNTHETIC")
