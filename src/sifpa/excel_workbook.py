"""`make excel`: the 2027 plan scenario model as an Excel workbook with live formulas.

Inputs (blue) -> PFS fees -> Drugs (price/dose inputs) -> Calc (per-drug formulas) -> Outputs (3 scenarios).
The same math as engine.py / scenarios.py; after writing, LibreOffice recalculates the file headless and
the recalculated Outputs are compared with outputs/scenarios.json (outputs/excel_recalc_check.json).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName

from sifpa import assumptions as A
from sifpa import engine as E
from sifpa.paths import OUTPUTS, ROOT

XLSX = ROOT / "excel" / "infusion_plan_2027_scenarios.xlsx"
BLUE = Font(color="1F4E9E")
BOLD = Font(bold=True)
HEAD = PatternFill("solid", fgColor="DDE5F0")


def _name(wb: Workbook, name: str, sheet: str, cell: str) -> None:
    wb.defined_names[name] = DefinedName(name, attr_text=f"'{sheet}'!${cell[0]}${cell[1:]}")


def _header(ws, row: int, labels: list[str]) -> None:
    for j, label in enumerate(labels, start=1):
        c = ws.cell(row=row, column=j, value=label)
        c.font, c.fill = BOLD, HEAD
        c.alignment = Alignment(wrap_text=True, vertical="top")


def build_inputs(wb: Workbook, con) -> None:
    ws = wb.create_sheet("Inputs")
    _header(ws, 1, ["Name", "Value", "Low", "High", "Source / label"])
    y = A.load()
    payers = E.payer_mix(con)
    rows: list[tuple] = []
    for key in ("asp_addon_pct", "biosimilar_ira_addon_pct", "sequestration_pct", "coinsurance_pct",
                "cf_2027_proposed", "mfp_payment_pct", "mfp_discount_vs_asp"):
        spec = y["policy"][key]
        rows.append((key, spec["value"], spec.get("low"), spec.get("high"), spec.get("source") or f"ASSUMPTION: {spec.get('why', '')}"))
    for key, spec in y["practice"].items():
        rows.append((key, spec["value"], spec.get("low"), spec.get("high"), spec.get("source") or f"ASSUMPTION: {spec.get('why', '')}"))
    rows.append(("ohio_ffs_share", round(payers["ohio_ffs_share"], 6), None, None,
                 "CMS Medicare Monthly Enrollment 2025 (Ohio counties): Original Medicare / total"))
    rows.append(("policy_shock_white_bagging", y["scenarios"]["policy_shock_white_bagging"]["value"], None, None,
                 "ASSUMPTION: " + y["scenarios"]["policy_shock_white_bagging"]["why"]))
    for i, (key, val, lo, hi, src) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=key)
        c = ws.cell(row=i, column=2, value=val)
        c.font = BLUE
        ws.cell(row=i, column=3, value=lo)
        ws.cell(row=i, column=4, value=hi)
        ws.cell(row=i, column=5, value=src)
        _name(wb, key, "Inputs", f"B{i}")
    r = len(rows) + 3
    ws.cell(row=r, column=1, value="Derived (formulas)").font = BOLD
    derived = [
        ("collect_factor", "=(1-coinsurance_pct)*(1-sequestration_pct)+coinsurance_pct*coinsurance_collection_rate",
         "Share of Medicare allowed collected: 80% x (1-2% sequestration) + 20% coinsurance x collection rate"),
        ("chair_cost_per_hour", "=rn_hourly_wage*(1+benefits_load)/chairs_per_rn+overhead_per_chair_hour",
         "RN cost per chair-hour + overhead"),
        ("w_commercial", "=payer_mix_commercial", "payer weight"),
        ("w_medicaid", "=payer_mix_medicaid", "payer weight"),
        ("w_medicare_ffs", "=(1-payer_mix_commercial-payer_mix_medicaid)*ohio_ffs_share", "Medicare x Ohio FFS share"),
        ("w_medicare_adv", "=(1-payer_mix_commercial-payer_mix_medicaid)*(1-ohio_ffs_share)", "Medicare x Ohio MA share"),
        ("booked_chair_hours", "=chairs*operating_days*chair_hours_per_day*chair_utilization", "annual capacity booked"),
    ]
    for k, (key, formula, note) in enumerate(derived, start=r + 1):
        ws.cell(row=k, column=1, value=key)
        ws.cell(row=k, column=2, value=formula)
        ws.cell(row=k, column=5, value=note)
        _name(wb, key, "Inputs", f"B{k}")
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["E"].width = 110


def build_pfs(wb: Workbook, con) -> None:
    ws = wb.create_sheet("PFS")
    loc = A.load()["locality"]
    df = con.sql(f"""
        select r.hcpcs, r.work_rvu, r.pe_rvu_nonfac, r.mp_rvu, g.pw_gpci, g.pe_gpci, g.mp_gpci
        from staging.stg_pfs_rvu r cross join (select * from staging.stg_pfs_gpci
          where state_abbr = '{loc["state_abbr"]}' and locality = '{loc["locality"]}') g
        where r.hcpcs in ('96365', '96366', '96372', '96413', '96415') order by 1
    """).df()
    _header(ws, 1, ["HCPCS", "Work RVU", "PE RVU (non-fac)", "MP RVU", "PW GPCI", "PE GPCI", "MP GPCI",
                    "Fee 2027 (proposed CF)"])
    for i, r in enumerate(df.itertuples(), start=2):
        for j, v in enumerate([r.hcpcs, r.work_rvu, r.pe_rvu_nonfac, r.mp_rvu, r.pw_gpci, r.pe_gpci, r.mp_gpci], start=1):
            ws.cell(row=i, column=j, value=v).font = BLUE if j > 1 else Font()
        ws.cell(row=i, column=8, value=f"=(B{i}*E{i}+C{i}*F{i}+D{i}*G{i})*cf_2027_proposed")
        _name(wb, f"fee_{r.hcpcs}", "PFS", f"H{i}")
    ws.cell(row=len(df) + 3, column=1, value="Source: CMS RVU26D (CY2026 RVUs) + CY2026 GPCI, Ohio statewide locality; "
            "CPT descriptors omitted (AMA copyright).")


DRUG_COLS = ["hcpcs", "molecule", "product_type", "admin_family", "units_per_admin", "asp_2027", "ref_asp_2027",
             "flag_addon_8pct", "ira_existing", "bio_rebuild_ok", "pl_2026q4", "admin_hours", "chair_hours",
             "mfp_selected", "mix_base", "mix_push"]


def build_drugs(wb: Workbook, drugs: pd.DataFrame) -> None:
    ws = wb.create_sheet("Drugs")
    _header(ws, 1, DRUG_COLS)
    for i, r in enumerate(drugs[DRUG_COLS].itertuples(index=False), start=2):
        for j, v in enumerate(r, start=1):
            if isinstance(v, float) and pd.isna(v):
                v = None
            if isinstance(v, bool | pd.BooleanDtype) or type(v).__name__ == "bool_":
                v = bool(v)
            c = ws.cell(row=i, column=j, value=v)
            if j > 4:
                c.font = BLUE
    ws.freeze_panes = "B2"


def build_calc(wb: Workbook, n: int) -> list[str]:
    """Per-drug formulas. Drugs sheet columns: E units, F asp, G ref_asp, H flag8, I ira_existing,
    J bio_ok, K pl_2026q4, L admin_hours, M chair_hours, N mfp_selected."""
    ws = wb.create_sheet("Calc")
    cols = {
        "A": ("hcpcs", "=Drugs!A{r}"),
        "B": ("addon_2027", '=IF(Drugs!C{r}="biosimilar",IF(Drugs!H{r},IF(Drugs!I{r},(3*biosimilar_ira_addon_pct+asp_addon_pct)/4,biosimilar_ira_addon_pct),asp_addon_pct),asp_addon_pct)'),
        "C": ("pl_2027", '=IF(Drugs!C{r}<>"biosimilar",Drugs!F{r}*(1+asp_addon_pct),IF(Drugs!J{r},Drugs!F{r}+B{r}*Drugs!G{r},Drugs!K{r}))'),
        "D": ("addon_hour_units", "=IF(Drugs!L{r}>1.5,ROUNDUP(Drugs!L{r}-1.5,0),0)"),
        "E": ("admin_allowed", '=IF(Drugs!D{r}="mab_infusion",fee_96413+D{r}*fee_96415,IF(Drugs!D{r}="iv_infusion",fee_96365+D{r}*fee_96366,IF(Drugs!D{r}="injection",fee_96372,0)))'),
        "F": ("acquisition_cost", "=Drugs!E{r}*Drugs!F{r}*(1+acquisition_spread_vs_asp)"),
        "G": ("chair_cost", "=Drugs!M{r}*chair_cost_per_hour"),
        "H": ("medicare_drug_revenue", "=Drugs!E{r}*C{r}*collect_factor"),
        "I": ("medicare_admin_revenue", "=E{r}*collect_factor"),
        "J": ("medicare_drug_margin", "=H{r}-F{r}"),
        "K": ("contribution_medicare_ffs", "=J{r}+I{r}-G{r}"),
        "L": ("contribution_medicare_adv", "=(J{r}+I{r})*ma_rate_vs_ffs-G{r}"),
        "M": ("commercial_drug_revenue", "=Drugs!E{r}*Drugs!F{r}*(1+commercial_drug_markup_vs_asp)"),
        "N": ("commercial_admin_revenue", "=E{r}*commercial_admin_multiple_of_medicare"),
        "O": ("contribution_commercial", "=M{r}-F{r}+N{r}-G{r}"),
        "P": ("contribution_commercial_whitebag", "=N{r}-G{r}"),
        "Q": ("medicaid_drug_revenue", "=Drugs!E{r}*Drugs!F{r}*(1+medicaid_drug_markup_vs_asp)"),
        "R": ("medicaid_admin_revenue", "=E{r}*medicaid_admin_multiple_of_medicare"),
        "S": ("contribution_medicaid", "=Q{r}-F{r}+R{r}-G{r}"),
        "T": ("medicare_drug_revenue_mfp", "=IF(Drugs!N{r},Drugs!E{r}*Drugs!F{r}*(1-mfp_discount_vs_asp)*(1+mfp_payment_pct)*collect_factor,H{r})"),
        "U": ("medicare_drug_margin_mfp", "=IF(Drugs!N{r},T{r}-Drugs!E{r}*Drugs!F{r}*(1-mfp_discount_vs_asp),J{r})"),
        "V": ("contribution_medicare_ffs_mfp", "=U{r}+I{r}-G{r}"),
        "W": ("contribution_medicare_adv_mfp", "=(U{r}+I{r})*ma_rate_vs_ffs-G{r}"),
        "X": ("blended_contribution_base", "=w_medicare_ffs*K{r}+w_medicare_adv*L{r}+w_commercial*O{r}+w_medicaid*S{r}"),
        "Y": ("blended_contribution_shock", "=w_medicare_ffs*V{r}+w_medicare_adv*W{r}+w_commercial*((1-policy_shock_white_bagging)*O{r}+policy_shock_white_bagging*P{r})+w_medicaid*S{r}"),
        "Z": ("blended_drug_revenue_base", "=w_medicare_ffs*H{r}+w_medicare_adv*H{r}*ma_rate_vs_ffs+w_commercial*M{r}+w_medicaid*Q{r}"),
        "AA": ("blended_admin_revenue", "=w_medicare_ffs*I{r}+w_medicare_adv*I{r}*ma_rate_vs_ffs+w_commercial*N{r}+w_medicaid*R{r}"),
        "AB": ("blended_drug_revenue_shock", "=w_medicare_ffs*T{r}+w_medicare_adv*T{r}*ma_rate_vs_ffs+w_commercial*(1-policy_shock_white_bagging)*M{r}+w_medicaid*Q{r}"),
    }
    for col, (label, _) in cols.items():
        c = ws[f"{col}1"]
        c.value, c.font, c.fill = label, BOLD, HEAD
    for r in range(2, n + 2):
        for col, (_, formula) in cols.items():
            ws[f"{col}{r}"] = formula.format(r=r)
    ws.freeze_panes = "B2"
    return list(cols)


def build_outputs(wb: Workbook, n: int) -> dict[str, str]:
    ws = wb.create_sheet("Outputs", 0)
    last = n + 1
    mix = {"base": f"Drugs!$O$2:$O${last}", "biosimilar_push": f"Drugs!$P$2:$P${last}", "policy_shock": f"Drugs!$O$2:$O${last}"}
    contrib = {"base": "X", "biosimilar_push": "X", "policy_shock": "Y"}
    drugrev = {"base": "Z", "biosimilar_push": "Z", "policy_shock": "AB"}
    ws["A1"] = "CY2027 infusion-suite plan: three scenarios (illustrative 12-chair suite; see Inputs)"
    ws["A1"].font = Font(bold=True, size=13)
    _header(ws, 3, ["Metric", "Base", "Biosimilar push", "Policy shock (2028 run-rate)"])
    metrics = [
        ("chair_hours_per_admin", "=SUMPRODUCT({mix},Drugs!$M$2:$M${last})/SUM({mix})"),
        ("contribution_per_admin", "=SUMPRODUCT({mix},Calc!${c}$2:${c}${last})/SUM({mix})"),
        ("drug_revenue_per_admin", "=SUMPRODUCT({mix},Calc!${d}$2:${d}${last})/SUM({mix})"),
        ("admin_revenue_per_admin", "=SUMPRODUCT({mix},Calc!$AA$2:$AA${last})/SUM({mix})"),
        ("administrations", "=booked_chair_hours/{col}4"),
        ("annual_contribution", "={col}5*{col}8"),
        ("annual_drug_revenue", "={col}6*{col}8"),
        ("annual_admin_revenue", "={col}7*{col}8"),
        ("contribution_per_chair", "={col}9/chairs"),
    ]
    cells: dict[str, str] = {}
    for i, (label, f) in enumerate(metrics, start=4):
        ws.cell(row=i, column=1, value=label)
        for j, sc in enumerate(("base", "biosimilar_push", "policy_shock"), start=2):
            col = "BCD"[j - 2]
            ws.cell(row=i, column=j, value=f.format(mix=mix[sc], c=contrib[sc], d=drugrev[sc], last=last, col=col))
            cells[f"{sc}.{label}"] = f"{col}{i}"
            ws.cell(row=i, column=j).number_format = "#,##0.00" if "per" in label else "#,##0"
    ws.column_dimensions["A"].width = 30
    for c in "BCD":
        ws.column_dimensions[c].width = 22
    ws["A15"] = ("Blue cells on Inputs/Drugs/PFS are inputs; everything on Calc and Outputs is a formula. "
                 "Change an input (e.g. Inputs!B for commercial_drug_markup_vs_asp) and the scenarios update.")
    ws["A16"] = "Prices: CMS ASP files + 2027 forecast (outputs/forecasts_quarterly_asp.csv). Mix: 2024 Medicare in-office, region."
    return cells


def recalc_with_libreoffice(src: Path) -> Path | None:
    """Headless LibreOffice re-saves the workbook, which evaluates every formula. Returns None if absent."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    out_dir = Path(tempfile.mkdtemp())
    subprocess.run([soffice, "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out_dir), str(src)],
                   check=True, capture_output=True, timeout=180)
    return out_dir / src.name


def main() -> None:
    con = E.connect()
    table = pd.read_csv(OUTPUTS / "scenario_drug_inputs.csv", dtype={"hcpcs": str})
    times = A.load()["infusion_time"]
    table["admin_hours"] = table["molecule"].map(lambda m: times[m]["admin_hours"])
    table["chair_hours"] = table["molecule"].map(lambda m: times[m]["chair_hours"])
    inj = table["admin_family"].eq("injection")
    table.loc[inj, ["admin_hours", "chair_hours"]] = [0.0, 0.5]  # same rule as engine.per_admin_economics
    table["bio_rebuild_ok"] = (table["product_type"] == "biosimilar") & table["ref_asp_2027"].notna() & ~table["asp_estimated"]

    wb = Workbook()
    wb.remove(wb.active)
    build_inputs(wb, con)
    build_pfs(wb, con)
    build_drugs(wb, table)
    build_calc(wb, len(table))
    cells = build_outputs(wb, len(table))
    readme = wb.create_sheet("README")
    for i, line in enumerate([
        "specialty-infusion-fpa: CY2027 in-office infusion plan (public data; illustrative practice).",
        "Flow: Inputs -> PFS -> Drugs -> Calc -> Outputs. All Calc/Outputs cells are live formulas.",
        "Scenarios: base (2027 forecast prices, proposed CY2027 CF, IRA +8% ends 2027-09-30 for existing biosimilars);",
        "biosimilar push (multi-source molecules to the target biosimilar share, lowest-ASP qualifying biosimilar);",
        "policy shock (2028 run-rate: Orencia/Entyvio at 106% of an ASSUMED MFP; commercial white bagging).",
        "Every assumption cell has its source or the label ASSUMPTION. Practice volumes/payer mix are illustrative.",
        "Generated by `make excel`; values verified against the Python model (outputs/excel_recalc_check.json).",
    ], start=1):
        readme.cell(row=i, column=1, value=line)
    XLSX.parent.mkdir(exist_ok=True)
    wb.save(XLSX)

    n_formulas = sum(1 for ws in wb.worksheets for row in ws.iter_rows() for c in row
                     if isinstance(c.value, str) and c.value.startswith("="))
    check = {"workbook": str(XLSX.relative_to(ROOT)), "n_formulas": n_formulas, "cells": cells}
    recalced = recalc_with_libreoffice(XLSX)
    if recalced:
        vals = load_workbook(recalced, data_only=True)["Outputs"]
        sc = json.loads((OUTPUTS / "scenarios.json").read_text())["scenarios"]
        comparisons = []
        for name in sc:
            for metric, py in (("annual_contribution", sc[name]["annual"]["contribution"]),
                               ("contribution_per_admin", sc[name]["per_admin"]["contribution"]),
                               ("administrations", sc[name]["annual"]["administrations"]),
                               ("annual_drug_revenue", sc[name]["annual"]["drug_revenue"])):
                xl = vals[cells[f"{name}.{metric}"]].value
                comparisons.append({"scenario": name, "metric": metric, "python": py, "excel": xl,
                                    "rel_diff": abs(xl - py) / abs(py) if py else None})
        check["libreoffice_recalc"] = True
        check["comparisons"] = comparisons
        check["max_rel_diff"] = max(c["rel_diff"] for c in comparisons)
    else:
        check["libreoffice_recalc"] = False
    (OUTPUTS / "excel_recalc_check.json").write_text(json.dumps(check, indent=2, default=float) + "\n")
    print(f"{XLSX.name}: {n_formulas} formulas; max rel diff vs Python = {check.get('max_rel_diff')}")


if __name__ == "__main__":
    main()
