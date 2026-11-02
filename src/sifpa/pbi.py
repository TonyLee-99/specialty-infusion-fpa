"""`make pbi`: write the Power BI Project (PBIP) with a TMDL semantic model over exports/*.csv.

NOT opened in Power BI Desktop (macOS build machine; ADR 0007). Structure is validated by
tests/test_tmdl.py and every measure has a SQL twin in sql/measures/ (written here from pbi_measures).
"""

from __future__ import annotations

import json
import uuid

import pandas as pd

from sifpa.paths import EXPORTS, ROOT
from sifpa.pbi_measures import MEASURES, slug

PBI = ROOT / "powerbi"
NAME = "SpecialtyInfusionFPA"
SM = PBI / f"{NAME}.SemanticModel"
DEF = SM / "definition"
SQL_DIR = ROOT / "sql" / "measures"
DATE_COLS = {"quarter_start", "date", "service_date", "submit_date", "remit_date", "month_start"}
TEXT_COLS = {"hcpcs", "npi", "county_fips", "market_id", "fips", "claim_id", "patient_id", "carc_code",
             "reference_hcpcs", "payment_quarter", "quarter_label", "zip5", "origin", "target", "quarter",
             "item_key", "site_id", "payer", "basis_quarter"}

RELATIONSHIPS = [  # (from table.column [many side], to table.column [one side])
    ("fact_asp_quarter", "hcpcs", "dim_drug", "hcpcs"),
    ("fact_asp_quarter", "quarter_start", "dim_date", "date"),
    ("fact_national_drug_year", "hcpcs", "dim_drug", "hcpcs"),
    ("fact_provider_drug_year", "hcpcs", "dim_drug", "hcpcs"),
    ("fact_provider_drug_year", "npi", "dim_provider", "npi"),
    ("fact_provider_scorecard", "npi", "dim_provider", "npi"),
    ("fact_provider_biosimilar", "npi", "dim_provider", "npi"),
    ("fact_margin_per_admin", "hcpcs", "dim_drug", "hcpcs"),
    ("fact_price_path", "hcpcs", "dim_drug", "hcpcs"),
    ("fact_plan_month", "site_id", "dim_site", "site_id"),
    ("fact_plan_month", "item_key", "dim_item", "item_key"),
    ("fact_plan_month", "month_start", "dim_date", "date"),
    ("fact_actual_month_SYNTHETIC", "site_id", "dim_site", "site_id"),
    ("fact_actual_month_SYNTHETIC", "item_key", "dim_item", "item_key"),
    ("fact_actual_month_SYNTHETIC", "month_start", "dim_date", "date"),
    ("fact_fixed_month", "site_id", "dim_site", "site_id"),
    ("fact_fixed_month", "month_start", "dim_date", "date"),
    ("dim_item", "hcpcs", "dim_drug", "hcpcs"),
    ("dim_provider", "county_fips", "dim_county_market", "county_fips"),
    ("dim_county_market", "market_id", "dim_market", "market_id"),
    ("fact_rcm_remits_SYNTHETIC", "claim_id", "fact_rcm_claims_SYNTHETIC", "claim_id"),
]


def tmdl_type(col: str, s: pd.Series) -> tuple[str, str]:
    """(TMDL dataType, Power Query type) for a CSV column."""
    if col in DATE_COLS:
        return "dateTime", "type date"
    if col in TEXT_COLS:
        return "string", "type text"
    if pd.api.types.is_bool_dtype(s) or set(s.dropna().astype(str).unique()) <= {"True", "False"} and s.notna().any():
        return "boolean", "type logical"
    if pd.api.types.is_integer_dtype(s):
        return "int64", "Int64.Type"
    if pd.api.types.is_float_dtype(s):
        return "double", "type number"
    return "string", "type text"


def q(name: str) -> str:
    """TMDL object names with spaces/symbols are single-quoted."""
    return f"'{name}'" if not name.replace("_", "").isalnum() else name


def table_tmdl(name: str, df: pd.DataFrame, measures: list[tuple]) -> str:
    tag = lambda: str(uuid.uuid5(uuid.NAMESPACE_URL, f"{name}/{len(lines)}"))  # noqa: E731 - stable ids
    lines: list[str] = []
    if name == "dim_date":
        lines += [f"table {name}", "\tdataCategory: Time", f"\tlineageTag: {tag()}", ""]
    else:
        lines += [f"table {q(name)}", f"\tlineageTag: {tag()}", ""]
    for _table, m_name, dax, folder, fmt, desc, context, _sql in measures:
        lines += [f"\t/// {desc} SQL twin context: {context}.", f"\tmeasure {q(m_name)} = {dax}", f"\t\tformatString: {fmt}",
                  f"\t\tdisplayFolder: {folder}", f"\t\tlineageTag: {tag()}", ""]
    types = []
    for col in df.columns:
        dt, pq = tmdl_type(col, df[col])
        types.append((col, pq))
        lines += [f"\tcolumn {q(col)}", f"\t\tdataType: {dt}"]
        if name == "dim_date" and col == "date":
            lines += ["\t\tisKey"]
        if dt in ("int64", "double") and not col.endswith(("_pctile", "year", "rank", "quarter_of_year", "month")):
            lines += ["\t\tsummarizeBy: sum"]
        else:
            lines += ["\t\tsummarizeBy: none"]
        lines += [f"\t\tlineageTag: {tag()}", f"\t\tsourceColumn: {col}", ""]
    typed = ", ".join(f'{{"{c}", {t}}}' for c, t in types)
    lines += [
        f"\tpartition {q(name)} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
        f'\t\t\t\t    Source = Csv.Document(File.Contents(RepoPath & "\\exports\\{name}.csv"), '
        '[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        "\t\t\t\t    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
        f'\t\t\t\t    Typed = Table.TransformColumnTypes(Promoted, {{{typed}}}, "en-US")',
        "\t\t\t\tin", "\t\t\t\t    Typed", "",
    ]
    if name.endswith("SYNTHETIC"):
        lines.insert(0, "/// SYNTHETIC data: revenue-cycle method demo only (ADR 0008). No business conclusion.")
    return "\n".join(lines) + "\n"


def main() -> None:
    (DEF / "tables").mkdir(parents=True, exist_ok=True)
    SQL_DIR.mkdir(parents=True, exist_ok=True)
    for old in list((DEF / "tables").glob("*.tmdl")) + list(SQL_DIR.glob("*.sql")):
        old.unlink()
    tables = sorted(p.stem for p in EXPORTS.glob("*.csv"))
    for t in tables:
        df = pd.read_csv(EXPORTS / f"{t}.csv", nrows=5000, dtype={c: str for c in TEXT_COLS})
        (DEF / "tables" / f"{t}.tmdl").write_text(table_tmdl(t, df, [m for m in MEASURES if m[0] == t]))
    rel = []
    for f_t, f_c, t_t, t_c in RELATIONSHIPS:
        rid = uuid.uuid5(uuid.NAMESPACE_URL, f"{f_t}.{f_c}->{t_t}.{t_c}")
        rel += [f"relationship {rid}", f"\tfromColumn: {q(f_t)}.{q(f_c)}", f"\ttoColumn: {q(t_t)}.{q(t_c)}", ""]
    (DEF / "relationships.tmdl").write_text("\n".join(rel))
    (DEF / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1600\n")
    (DEF / "expressions.tmdl").write_text(
        "/// Folder where this repo is cloned on the Windows machine that opens the PBIP.\n"
        'expression RepoPath = "C:\\\\repos\\\\specialty-infusion-fpa" meta [IsParameterQuery=true, Type="Text", '
        "IsParameterQueryRequired=true]\n\tlineageTag: 5a0c4f39-0000-4000-8000-000000000001\n")
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tdiscourageImplicitMeasures", "\tsourceQueryCulture: en-US", ""]
    model += [f"ref table {q(t)}" for t in tables]
    (DEF / "model.tmdl").write_text("\n".join(model) + "\n")
    (SM / "definition.pbism").write_text(json.dumps({"version": "4.0", "settings": {}}, indent=2) + "\n")
    report = PBI / f"{NAME}.Report"
    report.mkdir(exist_ok=True)
    (report / "definition.pbir").write_text(json.dumps(
        {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}, indent=2) + "\n")
    pages = ["Budget vs actual (SYNTHETIC actuals)", "Margin & pricing", "Growth & benchmark"]
    (report / "report.json").write_text(json.dumps({
        "config": json.dumps({"version": "5.43"}),
        "layoutOptimization": 0,
        "sections": [{"name": f"page{i}", "displayName": p, "displayOption": 1, "width": 1280, "height": 720,
                      "visualContainers": []} for i, p in enumerate(pages)],
        "note": "Page shells only. Build the visuals by hand with docs/powerbi_build_guide.md (expected numbers included).",
    }, indent=2) + "\n")
    (PBI / f"{NAME}.pbip").write_text(json.dumps({
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True}}, indent=2) + "\n")
    for m_table, m_name, *_rest, sql in MEASURES:
        (SQL_DIR / f"{slug(m_name)}.sql").write_text(
            f"-- SQL twin of DAX measure [{m_name}] (table {m_table}); context: {_rest[-1]}; DuckDB over exports/*.csv\n{sql}\n")
    print(f"PBIP written: {len(tables)} tables, {len(MEASURES)} measures, {len(RELATIONSHIPS)} relationships")


if __name__ == "__main__":
    main()
