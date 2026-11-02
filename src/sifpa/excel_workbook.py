"""`make excel`: the CY2027 plan as an Excel workbook with live formulas (mirrors engine.py).

Inputs (blue) -> PFS fees -> Drugs (2027 price/dose/mix inputs from the Python price path) -> Calc
(per-drug x payer formulas) -> Outputs (base / biosimilar on listed products / 2028 policy) -> Monthly.

Check: the workbook is built twice (default inputs and a STRESSED input set that moves MA rate, commercial
markup, coinsurance collection, panel and chairs), each recalculated by headless LibreOffice and compared
with engine.build() under the same inputs -> outputs/excel_recalc_check.json. tests/test_excel.py re-runs
the recalculation live wherever LibreOffice is installed (CI installs it).
"""

from __future__ import annotations

import calendar
import datetime as dt
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
BLUE, BOLD = Font(color="1F4E9E"), Font(bold=True)
HEAD = PatternFill("solid", fgColor="DDE5F0")
STRESS = {"ma_rate_vs_ffs": 0.95, "commercial_drug_markup_vs_asp": 0.10, "coinsurance_collection_rate": 0.80,
          "panel_patients": 2600, "chairs": 10, "denial_writeoff_commercial": 0.05}
PAYER_COLS = {"medicare_ffs": "FFS", "medicare_adv": "MA", "commercial": "COM", "medicaid": "MCD"}


def _name(wb, name, sheet, cell):
    col = "".join(ch for ch in cell if ch.isalpha())
    row = "".join(ch for ch in cell if ch.isdigit())
    wb.defined_names[name] = DefinedName(name, attr_text=f"'{sheet}'!${col}${row}")


def _header(ws, row, labels):
    for j, label in enumerate(labels, start=1):
        c = ws.cell(row=row, column=j, value=label)
        c.font, c.fill, c.alignment = BOLD, HEAD, Alignment(wrap_text=True, vertical="top")


def weekdays_2027() -> list[int]:
    return [sum(1 for d in range(1, calendar.monthrange(2027, m)[1] + 1) if dt.date(2027, m, d).weekday() < 5)
            for m in range(1, 13)]


def build_inputs(wb, con, overrides):
    ws = wb.create_sheet("Inputs")
    _header(ws, 1, ["Name", "Value", "Low", "High", "Source / label"])
    y = A.load()
    rows = []
    for key in ("asp_addon_pct", "biosimilar_ira_addon_pct", "sequestration_pct", "coinsurance_pct",
                "cf_2027_proposed", "mfp_payment_pct", "mfp_discount_vs_asp"):
        s = y["policy"][key]
        rows.append((key, s["value"], s.get("low"), s.get("high"), s.get("source") or "ASSUMPTION: " + s.get("why", "")))
    for key, s in y["practice"].items():
        rows.append((key, overrides.get(key, s["value"]), s.get("low"), s.get("high"),
                     s.get("source") or "ASSUMPTION: " + s.get("why", "")))
    ffs = E.payer_shares(con)["medicare_ffs"] / (1 - A.practice()["payer_mix_commercial"] - A.practice()["payer_mix_medicaid"])
    rows.append(("ohio_ffs_share", round(ffs, 8), None, None, "CMS Medicare Monthly Enrollment 2025 (Ohio): Original Medicare / total"))
    sc = y["scenarios"]
    tiers = sc["white_bagging_by_cost_tier"]["value"]
    for k in ("above_10k", "from_3k_to_10k", "below_3k", "threshold_high", "threshold_low"):
        rows.append((f"wb_{k}", tiers[k], None, None, "ASSUMPTION: " + sc["white_bagging_by_cost_tier"]["why"]))
    for k in ("ivs_recapture_share", "ivs_dispensing_margin"):
        rows.append((k, sc[k]["value"], sc[k].get("low"), sc[k].get("high"), "ASSUMPTION: " + sc[k]["why"]))
    for i, (key, val, lo, hi, src) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=key)
        ws.cell(row=i, column=2, value=val).font = BLUE
        ws.cell(row=i, column=3, value=lo)
        ws.cell(row=i, column=4, value=hi)
        ws.cell(row=i, column=5, value=src)
        _name(wb, key, "Inputs", f"B{i}")
    r = len(rows) + 3
    ws.cell(row=r, column=1, value="Derived (formulas)").font = BOLD
    derived = [
        ("collect_FFS", "=((1-coinsurance_pct)*(1-sequestration_pct)+coinsurance_pct*coinsurance_collection_rate)*(1-denial_writeoff_medicare)", "Medicare FFS net collection on allowed"),
        ("collect_MA", "=((1-coinsurance_pct)*(1-sequestration_pct)+coinsurance_pct*coinsurance_collection_rate)*ma_rate_vs_ffs*(1-denial_writeoff_commercial)", "MA: FFS-like terms x MA rate, prior-auth denials"),
        ("collect_COM", "=(1-commercial_patient_resp_share*(1-patient_collection_rate))*(1-denial_writeoff_commercial)*(1-underpayment_commercial)", "Commercial: patient bad debt, denials, underpayment"),
        ("collect_MCD", "=1-denial_writeoff_commercial", "Medicaid"),
        ("share_COM", "=payer_mix_commercial", "patient share"), ("share_MCD", "=payer_mix_medicaid", "patient share"),
        ("share_FFS", "=(1-payer_mix_commercial-payer_mix_medicaid)*ohio_ffs_share", "patient share"),
        ("share_MA", "=(1-payer_mix_commercial-payer_mix_medicaid)*(1-ohio_ffs_share)", "patient share"),
        ("capacity_hours", "=chairs*operating_days*chair_hours_per_day", "chair-hours available"),
        ("fixed_nursing", "=chairs/chairs_per_rn*operating_days*chair_hours_per_day*rn_hourly_wage*(1+benefits_load)", "RNs staffed for open hours (fixed)"),
        ("fixed_total", "=fixed_nursing+chairs*rent_equipment_per_chair_year+site_fixed_staff_per_year", "all fixed costs"),
        ("recapture_rate", "=ivs_recapture_share*ivs_dispensing_margin", "Owned-pharmacy margin on white-bagged drug cost"),
    ]
    for payer, tag in PAYER_COLS.items():
        n = "neuro_share_medicare" if payer.startswith("medicare") else "neuro_share_commercial"
        derived += [(f"lw_neuro_{tag}", f"={n}", f"{payer} neurology line weight"),
                    (f"lw_imm_{tag}", f"=(1-{n})*immunology_share_of_non_neuro", f"{payer} immunology line weight"),
                    (f"lw_rheum_{tag}", f"=1-{n}-(1-{n})*immunology_share_of_non_neuro", f"{payer} rheum line weight")]
    for k, (key, formula, note) in enumerate(derived, start=r + 1):
        ws.cell(row=k, column=1, value=key)
        ws.cell(row=k, column=2, value=formula)
        ws.cell(row=k, column=5, value=note)
        _name(wb, key, "Inputs", f"B{k}")
    ws.column_dimensions["A"].width, ws.column_dimensions["E"].width = 34, 110


def build_pfs(wb, con):
    ws = wb.create_sheet("PFS")
    df = con.sql("""select r.hcpcs, r.work_rvu, r.pe_rvu_nonfac, r.mp_rvu, g.pw_gpci, g.pe_gpci, g.mp_gpci
                    from staging.stg_pfs_rvu r cross join (select * from staging.stg_pfs_gpci where state_abbr = 'OH'
                    and locality = '00') g where r.hcpcs in ('96365','96366','96372','96413','96415') order by 1""").df()
    _header(ws, 1, ["HCPCS", "Work RVU", "PE RVU (non-fac)", "MP RVU", "PW GPCI", "PE GPCI", "MP GPCI", "Fee (CY2027 proposed CF)"])
    for i, r in enumerate(df.itertuples(), start=2):
        for j, v in enumerate([r.hcpcs, r.work_rvu, r.pe_rvu_nonfac, r.mp_rvu, r.pw_gpci, r.pe_gpci, r.mp_gpci], start=1):
            ws.cell(row=i, column=j, value=v).font = BLUE if j > 1 else Font()
        ws.cell(row=i, column=8, value=f"=(B{i}*E{i}+C{i}*F{i}+D{i}*G{i})*cf_2027_proposed")
        _name(wb, f"fee_{r.hcpcs}", "PFS", f"H{i}")
    ws.cell(row=len(df) + 3, column=1, value="CY2026 RVUs + GPCI (Ohio statewide) with the CY2027 PROPOSED CF; CPT descriptors omitted (AMA copyright).")


DRUG_COLS = ["hcpcs", "molecule", "product_type", "admin_family", "line", "units_per_admin", "admins_per_patient_year",
             "admin_hours", "chair_hours", "pl_2027", "pay_asp_2027", "buy_asp_2027", "pl_2028_rules", "flag_lesser_of",
             "ipay2028_selected", "growth", "ws_base", "ws_listed"]
# Drugs sheet column letters (1-based order above)
DC = {c: chr(ord("A") + i) for i, c in enumerate(DRUG_COLS)}


def build_drugs(wb, drugs: pd.DataFrame):
    ws = wb.create_sheet("Drugs")
    _header(ws, 1, DRUG_COLS)
    for i, r in enumerate(drugs[DRUG_COLS].itertuples(index=False), start=2):
        for j, v in enumerate(r, start=1):
            if isinstance(v, float) and pd.isna(v):
                v = None
            if type(v).__name__ in ("bool_", "bool"):
                v = bool(v)
            ws.cell(row=i, column=j, value=v).font = BLUE if j > 5 else Font()
    ws.freeze_panes = "B2"


def calc_columns() -> dict[str, tuple[str, str]]:
    """Calc sheet: one row per drug; every cell a formula over Drugs!row and named inputs."""
    d = lambda c: f"Drugs!{DC[c]}{{r}}"  # noqa: E731
    cols: dict[str, tuple[str, str]] = {
        "A": ("hcpcs", f"={d('hcpcs')}"),
        "B": ("addon_hour_units", f"=IF({d('admin_hours')}>1.5,ROUNDUP({d('admin_hours')}-1.5,0),0)"),
        "C": ("admin_allowed", f'=IF({d("admin_family")}="mab_infusion",fee_96413+B{{r}}*fee_96415,IF({d("admin_family")}="iv_infusion",fee_96365+B{{r}}*fee_96366,IF({d("admin_family")}="injection",fee_96372,0)))'),
        "D": ("acquisition", f"={d('units_per_admin')}*{d('buy_asp_2027')}*(1+acquisition_spread_vs_asp+IF({d('flag_lesser_of')},lesser_of_acquisition_premium,0))"),
        "E": ("acquisition_mfp", f"=IF({d('ipay2028_selected')},D{{r}}*(1-mfp_discount_vs_asp),D{{r}})"),
        "F": ("variable", "=variable_cost_per_infusion"),
        "G": ("contrib_FFS", f"=({d('units_per_admin')}*{d('pl_2027')}+C{{r}})*collect_FFS-D{{r}}-F{{r}}"),
        "H": ("contrib_MA", f"=({d('units_per_admin')}*{d('pl_2027')}+C{{r}})*collect_MA-D{{r}}-F{{r}}"),
        "I": ("contrib_COM", f"=({d('units_per_admin')}*{d('pay_asp_2027')}*(1+commercial_drug_markup_vs_asp)+C{{r}}*commercial_admin_multiple_of_medicare)*collect_COM-D{{r}}-F{{r}}"),
        "J": ("contrib_MCD", f"=({d('units_per_admin')}*{d('pay_asp_2027')}*(1+medicaid_drug_markup_vs_asp)+C{{r}}*medicaid_admin_multiple_of_medicare)*collect_MCD-D{{r}}-F{{r}}"),
        # 2028 rules: IRA add-on back to 6% (pl_2028_rules), MFP for selected drugs (Medicare only), white bagging
        "K": ("contrib_FFS_2028", f"=IF({d('ipay2028_selected')},({d('units_per_admin')}*{d('pl_2028_rules')}*(1-mfp_discount_vs_asp)+C{{r}})*collect_FFS-E{{r}}-F{{r}},({d('units_per_admin')}*{d('pl_2028_rules')}+C{{r}})*collect_FFS-D{{r}}-F{{r}})"),
        "L": ("contrib_MA_2028", f"=IF({d('ipay2028_selected')},({d('units_per_admin')}*{d('pl_2028_rules')}*(1-mfp_discount_vs_asp)+C{{r}})*collect_MA-E{{r}}-F{{r}},({d('units_per_admin')}*{d('pl_2028_rules')}+C{{r}})*collect_MA-D{{r}}-F{{r}})"),
        "M": ("wb_share", "=IF(D{r}>wb_threshold_high,wb_above_10k,IF(D{r}>=wb_threshold_low,wb_from_3k_to_10k,wb_below_3k))"),
        "N": ("contrib_COM_whitebag", "=C{r}*commercial_admin_multiple_of_medicare*collect_COM-F{r}+recapture_rate*D{r}"),
        "O": ("contrib_COM_2028", "=(1-M{r})*I{r}+M{r}*N{r}"),
    }
    # admins per payer, base and listed-product mix: panel x payer share x line weight x within-line share x admins/pt x growth
    letters = iter(["P", "Q", "R", "S", "T", "U", "V", "W"])
    for mixcol in ("ws_base", "ws_listed"):
        for tag in PAYER_COLS.values():
            line = d("line")
            lw = f'IF({line}="neuro",lw_neuro_{tag},IF({line}="immunology",lw_imm_{tag},lw_rheum_{tag}))'
            cols[next(letters)] = (f"admins_{tag}_{mixcol}",
                                   f"=panel_patients*share_{tag}*{lw}*{d(mixcol)}*{d('admins_per_patient_year')}*{d('growth')}")
    cols["X"] = ("chair_hours_base", f"=SUM(P{{r}}:S{{r}})*{d('chair_hours')}")
    cols["Y"] = ("chair_hours_listed", f"=SUM(T{{r}}:W{{r}})*{d('chair_hours')}")
    cols["Z"] = ("contrib_base", "=P{r}*G{r}+Q{r}*H{r}+R{r}*I{r}+S{r}*J{r}")
    cols["AA"] = ("contrib_listed", "=T{r}*G{r}+U{r}*H{r}+V{r}*I{r}+W{r}*J{r}")
    cols["AB"] = ("contrib_2028", "=P{r}*K{r}+Q{r}*L{r}+R{r}*O{r}+S{r}*J{r}")
    cols["AC"] = ("contrib_commercial_base", "=R{r}*I{r}")
    return cols


def build_calc(wb, n: int):
    ws = wb.create_sheet("Calc")
    cols = calc_columns()
    for col, (label, _) in cols.items():
        c = ws[f"{col}1"]
        c.value, c.font, c.fill = label, BOLD, HEAD
    for r in range(2, n + 2):
        for col, (_, f) in cols.items():
            ws[f"{col}{r}"] = f.format(r=r)
    ws.freeze_panes = "B2"


def build_outputs(wb, n: int) -> dict[str, str]:
    ws = wb.create_sheet("Outputs", 0)
    last = n + 1
    rng = lambda c: f"Calc!${c}$2:${c}${last}"  # noqa: E731
    ws["A1"] = "CY2027 plan, illustrative 12-chair suite (see Inputs). Prices: 2027 average on the lagged ASP path."
    ws["A1"].font = Font(bold=True, size=13)
    _header(ws, 3, ["Metric", "Base", "Biosimilar (listed products)", "Policy 2028 run-rate"])
    spec = {
        "base": ("P", "S", "X", "Z"), "biosimilar_listed": ("T", "W", "Y", "AA"), "policy_2028": ("P", "S", "X", "AB")}
    metrics = ["demand_admins", "demand_chair_hours", "served_share", "administrations", "utilization", "contribution",
               "fixed_costs", "operating_margin", "contribution_per_admin"]
    cells = {}
    for j, (sc, (a0, a1, hcol, ccol)) in enumerate(spec.items(), start=2):
        col = "BCD"[j - 2]
        f = {
            "demand_admins": f"=SUM(Calc!${a0}$2:${a1}${last})",
            "demand_chair_hours": f"=SUM({rng(hcol)})",
            "served_share": f"=MIN(1,capacity_hours/{col}5)",
            "administrations": f"={col}4*{col}6",
            "utilization": f"={col}5*{col}6/capacity_hours",
            "contribution": f"=SUM({rng(ccol)})*{col}6",
            "fixed_costs": "=fixed_total",
            "operating_margin": f"={col}9-{col}10",
            "contribution_per_admin": f"={col}9/{col}7",
        }
        for i, mname in enumerate(metrics, start=4):
            ws.cell(row=i, column=1, value=mname)
            ws.cell(row=i, column=j, value=f[mname]).number_format = "0.0%" if mname in ("utilization", "served_share") else "#,##0"
            cells[f"{sc}.{mname}"] = f"{col}{i}"
    ws.column_dimensions["A"].width = 30
    for c in "BCD":
        ws.column_dimensions[c].width = 24
    ws["A15"] = "Blue cells on Inputs/Drugs/PFS are inputs; Calc, Outputs and Monthly are formulas."
    ws["A16"] = "Lag: pl_2027 is paid on ASP(t-2); buy_asp_2027 is ASP(t) (outputs/price_path.csv)."
    return cells


def build_monthly(wb, cells):
    ws = wb.create_sheet("Monthly")
    _header(ws, 1, ["Month", "Weekdays", "Administrations", "Contribution", "Fixed costs", "Operating margin"])
    wd = weekdays_2027()
    for m, days in enumerate(wd, start=2):
        ws.cell(row=m, column=1, value=calendar.month_abbr[m - 1] + " 2027")
        ws.cell(row=m, column=2, value=days).font = BLUE
        ws.cell(row=m, column=3, value=f"=Outputs!{cells['base.administrations']}*B{m}/SUM($B$2:$B$13)")
        ws.cell(row=m, column=4, value=f"=Outputs!{cells['base.contribution']}*B{m}/SUM($B$2:$B$13)")
        ws.cell(row=m, column=5, value="=fixed_total/12")
        ws.cell(row=m, column=6, value=f"=D{m}-E{m}")
    ws.cell(row=15, column=1, value="Volume phased by operating weekdays at 2027-average unit economics; quarterly "
                                     "price steps (incl. the 2027Q4 IRA change) are in outputs/plan_prices_quarterly.csv.")


def drug_inputs() -> pd.DataFrame:
    t = pd.read_csv(OUTPUTS / "scenario_drug_inputs.csv", dtype={"hcpcs": str})
    mix = pd.read_csv(OUTPUTS / "scenario_mix.csv", dtype={"hcpcs": str})
    # within-line share = payer share / payer line weight; identical across payers by construction
    lw = {"neuro": A.practice()["neuro_share_medicare"]}
    imm = (1 - lw["neuro"]) * A.practice()["immunology_share_of_non_neuro"]
    lw.update({"immunology": imm, "rheum": 1 - lw["neuro"] - imm})
    ffs = mix[mix["payer"] == "medicare_ffs"].copy()
    ffs["ws_base"] = ffs["share_base"] / ffs["line"].map(lw)
    ffs["ws_listed"] = ffs["share_listed"] / ffs["line"].map(lw)
    t = t.merge(ffs[["hcpcs", "line", "ws_base", "ws_listed"]], on="hcpcs", how="left")
    t["line"] = t["line"].fillna("none")
    t[["ws_base", "ws_listed"]] = t[["ws_base", "ws_listed"]].fillna(0.0)
    growth = E.demand_growth(t)
    t["growth"] = t["hcpcs"].map(growth).fillna(1.0)
    return t


def write_workbook(con, path: Path, overrides: dict) -> dict[str, str]:
    t = drug_inputs()
    wb = Workbook()
    wb.remove(wb.active)
    build_inputs(wb, con, overrides)
    build_pfs(wb, con)
    build_drugs(wb, t)
    build_calc(wb, len(t))
    cells = build_outputs(wb, len(t))
    build_monthly(wb, cells)
    readme = wb.create_sheet("README")
    for i, line in enumerate([
        "specialty-infusion-fpa: CY2027 in-office infusion plan (public data; illustrative practice).",
        "Flow: Inputs -> PFS -> Drugs -> Calc -> Outputs -> Monthly. Calc/Outputs/Monthly are live formulas.",
        "Volume is demand-driven: patients x payer share x service-line weight x within-line share x admins/patient.",
        "Net revenue: every payer has a collection factor (Inputs: collect_FFS / MA / COM / MCD).",
        "Drug cost uses buy_asp_2027 (ASP in the purchase quarter); Medicare pays pl_2027 (ASP two quarters earlier + add-on).",
        "Every assumption has its source or the label ASSUMPTION. Practice volumes/payer mix are illustrative.",
    ], start=1):
        readme.cell(row=i, column=1, value=line)
    path.parent.mkdir(exist_ok=True)
    wb.properties.created = wb.properties.modified = dt.datetime(2026, 11, 2)  # stable rebuilds
    wb.save(path)
    return cells


def recalc(src: Path) -> Path | None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    out = Path(tempfile.mkdtemp())
    subprocess.run([soffice, "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), str(src)],
                   check=True, capture_output=True, timeout=240)
    return out / src.name


def python_expectation(con, overrides: dict) -> dict:
    """Independent computation of the same Outputs through engine.build() with the same inputs."""
    from sifpa import scenarios as S
    o = dict(overrides)
    chairs, panel = o.pop("chairs", None), o.pop("panel_patients", None)
    base = E.build(con, overrides=o, chairs=chairs, panel=panel)
    listed = E.build(con, overrides=o, chairs=chairs, panel=panel,
                     mix_override=S.push_listed_mix(base["mix"], base["drugs"]))
    p28 = E.build(con, overrides=o, chairs=chairs, panel=panel, rules_year=2028, mfp=True, white_bag=True)
    return {name: {"administrations": r["pnl"]["administrations"], "contribution": r["pnl"]["contribution"],
                   "operating_margin": r["pnl"]["operating_margin"], "utilization": r["pnl"]["utilization"]}
            for name, r in (("base", base), ("biosimilar_listed", listed), ("policy_2028", p28))}


def compare(con, overrides: dict, label: str) -> dict:
    tmp = Path(tempfile.mkdtemp()) / XLSX.name
    path = XLSX if not overrides else tmp
    cells = write_workbook(con, path, overrides)
    rec = recalc(path)
    if rec is None:
        return {"case": label, "libreoffice_recalc": False}
    vals = load_workbook(rec, data_only=True)["Outputs"]
    exp = python_expectation(con, overrides)
    comps = []
    for sc, metrics in exp.items():
        for metric, py in metrics.items():
            xl = vals[cells[f"{sc}.{metric}"]].value
            comps.append({"scenario": sc, "metric": metric, "python": py, "excel": xl,
                          "rel_diff": abs(xl - py) / max(abs(py), 1e-9)})
    return {"case": label, "inputs": overrides, "libreoffice_recalc": True, "comparisons": comps,
            "max_rel_diff": max(c["rel_diff"] for c in comps)}


def main() -> None:
    con = E.connect()
    default = compare(con, {}, "default inputs")
    stressed = compare(con, STRESS, "stressed inputs")
    wb = load_workbook(XLSX)
    n_formulas = sum(1 for ws in wb.worksheets for row in ws.iter_rows() for c in row
                     if isinstance(c.value, str) and c.value.startswith("="))
    check = {"workbook": str(XLSX.relative_to(ROOT)), "n_formulas": n_formulas, "cases": [default, stressed],
             "max_rel_diff": max(c.get("max_rel_diff", 0) for c in (default, stressed)),
             "note": "LOCAL check generated by `make excel`; tests/test_excel.py repeats it live where LibreOffice exists (CI installs it)."}
    (OUTPUTS / "excel_recalc_check.json").write_text(json.dumps(check, indent=2, default=float) + "\n")
    print(f"{XLSX.name}: {n_formulas} formulas; max rel diff default {default.get('max_rel_diff')}, stressed {stressed.get('max_rel_diff')}")


if __name__ == "__main__":
    main()
