"""The plan engine: 2027 prices with the real 2-quarter ASP lag, per-infusion economics by drug and
payer (with net-revenue haircuts for every payer), a formulary-relevant drug mix by payer, and a
demand-driven suite P&L with fixed and variable costs.

margin.py, scenarios.py, the Excel workbook and the Power BI budget table all call this module, so one
set of formulas produces every infusion number (ADRs 0003, 0006, 0009).

Price timing (ADR 0003): Medicare pays in quarter q on ASP(q-2) (+6%, or + k x reference ASP for a
biosimilar); the practice buys in quarter q at ASP(q). Both come from outputs/price_path.csv
(forecast.py), indexed by ASP basis quarter.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import duckdb
import numpy as np
import pandas as pd

from sifpa import assumptions as A
from sifpa import mechanics as M
from sifpa.paths import OUTPUTS, WAREHOUSE

INFUSION_FAMILIES = {"mab_infusion": ("96413", "96415"), "iv_infusion": ("96365", "96366"), "injection": ("96372", None)}
CHAIR_FAMILIES = ("mab_infusion", "iv_infusion")
PLAN_QUARTERS = ["2027Q1", "2027Q2", "2027Q3", "2027Q4"]
IRA_EXISTING_LAST_FIRST_QUARTER = "2022Q3"  # paid under ASP by 2022-09-30 -> +8% window ends 2027-09-30
PAYERS = ("medicare_ffs", "medicare_adv", "commercial", "medicaid")
SPECIALTIES = ("Rheumatology", "Neurology", "Gastroenterology", "Allergy/ Immunology")  # CMS spelling has a space
# Service lines of a regional inflammatory-disease practice and the specialty whose in-office mix defines each line
LINES = {"neuro": ("Neurology",), "rheum": ("Rheumatology",),
         "immunology": ("Neurology", "Rheumatology", "Allergy/ Immunology", "Gastroenterology")}
LINE_MOLECULES = {"neuro": ("ocrelizumab", "natalizumab", "ublituximab", "alemtuzumab", "eptinezumab"),
                  "rheum": ("infliximab", "rituximab", "belimumab"),
                  "immunology": ("immune_globulin",)}
# Full-formulary variant: also the non-listed chair molecules those specialties infuse (MFP exposure check)
EXTRA_MOLECULES = {"neuro": ("eculizumab", "efgartigimod", "ravulizumab", "inebilizumab"),
                   "rheum": ("abatacept", "golimumab", "tocilizumab", "pegloticase"),
                   "immunology": ()}


def connect() -> duckdb.DuckDBPyConnection:
    """Full warehouse by default; SIFPA_WAREHOUSE points tests at the committed-fixture warehouse."""
    return duckdb.connect(os.environ.get("SIFPA_WAREHOUSE", str(WAREHOUSE)), read_only=True)


def mg_per_unit(billing_unit: str) -> float:
    """'10 MG' -> 10.0; '1 UNIT' -> 1.0 (botulinum units are their own unit)."""
    m = re.match(r"([\d.]+)", str(billing_unit))
    return float(m.group(1)) if m else 1.0


def quarter_add(q: str, k: int) -> str:
    y, n = int(q[:4]), int(q[-1]) - 1 + k
    return f"{y + n // 4}Q{n % 4 + 1}"


# ---------------------------------------------------------------- drugs, dose, prices
def drug_frame(con) -> pd.DataFrame:
    """Catalog drugs priced in the latest ASP file, with observed dose and administrations per patient.

    Dose = units / beneficiary-day (2024 national in-office Medicare), pooled to the molecule in mg so new
    biosimilar codes inherit their molecule's dose. Administrations per patient-year = bene-days / benes.
    """
    latest = con.sql("select max(payment_quarter) from marts.fct_asp_quarter").fetchall()[0][0]
    df = con.sql(f"""
        select d.hcpcs, d.molecule, d.brand, d.product_type, d.reference_hcpcs, d.admin_family,
               d.formulary_listed, d.ipay2028_selected, d.billing_unit,
               p.payment_limit as pl_latest, p.addon_pct, p.flag_addon_8pct, p.flag_lesser_of,
               p.asp_basis is null as asp_estimated
        from marts.dim_drug d
        join marts.fct_asp_quarter p on p.hcpcs = d.hcpcs and p.payment_quarter = '{latest}'
    """).df()
    first = con.sql("select hcpcs, min(payment_quarter) as first_q from marts.fct_asp_quarter group by 1").df()
    df = df.merge(first, on="hcpcs")
    df["mg_per_unit"] = df["billing_unit"].map(mg_per_unit)
    dose = con.sql("""
        select d.molecule, d.billing_unit, n.services, n.bene_day_services, n.benes
        from marts.fct_national_drug_year n join marts.dim_drug d using (hcpcs)
        where n.year = 2024 and n.place_of_service = 'O' and n.bene_day_services > 0
    """).df()
    dose["mg"] = dose["services"] * dose["billing_unit"].map(mg_per_unit)
    mol = dose.groupby("molecule").agg(mg=("mg", "sum"), admins=("bene_day_services", "sum"), benes=("benes", "sum"))
    mol["dose_mg"] = mol["mg"] / mol["admins"]
    mol["admins_per_patient_year"] = mol["admins"] / mol["benes"]
    df = df.merge(mol[["dose_mg", "admins_per_patient_year"]], left_on="molecule", right_index=True, how="left")
    df["units_per_admin"] = df["dose_mg"] / df["mg_per_unit"]
    times = A.load()["infusion_time"]
    df["admin_hours"] = df["molecule"].map(lambda m: times[m]["admin_hours"])
    df["chair_hours"] = df["molecule"].map(lambda m: times[m]["chair_hours"])
    inj = df["admin_family"].eq("injection")
    df.loc[inj, ["admin_hours", "chair_hours"]] = [0.0, 0.5]  # e.g. ocrelizumab subcutaneous J2351
    df["ira_existing"] = (df["product_type"] == "biosimilar") & (df["first_q"] <= IRA_EXISTING_LAST_FIRST_QUARTER)
    return df


def load_price_path() -> pd.DataFrame:
    return pd.read_csv(OUTPUTS / "price_path.csv", dtype={"hcpcs": str})


def addon_for(row, quarter: str, rules_year: int) -> float:
    """Add-on % applied in `quarter`: 6% of own ASP, or for an 8%-flagged biosimilar 8% of reference ASP
    until its IRA window ends (existing biosimilars: after 2027-09-30)."""
    asp_addon, ira = A.value("policy", "asp_addon_pct"), A.value("policy", "biosimilar_ira_addon_pct")
    if row.product_type != "biosimilar" or not row.flag_addon_8pct:
        return asp_addon
    if row.ira_existing and (rules_year >= 2028 or quarter > "2027Q3"):
        return asp_addon
    return ira


def plan_prices(drugs: pd.DataFrame, path: pd.DataFrame, rules_year: int = 2027,
                asp_scale: dict[str, float] | None = None, buy_over_pay: dict[str, float] | None = None):
    """Quarterly 2027 payment limit (on lagged ASP) and acquisition ASP (current quarter) per HCPCS.

    asp_scale optionally rescales a code's whole ASP path (e.g. an MFP replaces ASP for Medicare).
    """
    asp = path.set_index(["hcpcs", "basis_quarter"])
    rows = []
    for r in drugs.itertuples():
        scale = (asp_scale or {}).get(r.hcpcs, 1.0)
        for q in PLAN_QUARTERS:
            pay_q, buy_q = quarter_add(q, -2), q

            def a(code, bq):
                v = asp["asp"].get((code, bq))
                return np.nan if v is None else float(v)

            pay_asp, buy_asp = a(r.hcpcs, pay_q) * scale, a(r.hcpcs, buy_q) * scale
            if buy_over_pay and r.hcpcs in buy_over_pay:  # lag-drift scenario: ASP(t) = ASP(t-2) x factor
                buy_asp = pay_asp * buy_over_pay[r.hcpcs]
            addon = addon_for(r, q, rules_year)
            ref_pay = a(r.reference_hcpcs, pay_q) if isinstance(r.reference_hcpcs, str) and r.reference_hcpcs else np.nan
            if r.product_type == "biosimilar" and not r.asp_estimated and not np.isnan(ref_pay):
                pl = pay_asp + addon * ref_pay  # add-on is computed on the REFERENCE product's ASP
            elif r.asp_estimated and r.product_type == "biosimilar":
                pl = pay_asp * (1 + r.addon_pct)  # non-ASP-priced biosimilar: path is PL/(1+add-on)
            else:
                pl = pay_asp * (1 + A.value("policy", "asp_addon_pct"))
            rows.append({"hcpcs": r.hcpcs, "quarter": q, "pay_asp": pay_asp, "buy_asp": buy_asp,
                         "addon": addon, "payment_limit": pl})
    q = pd.DataFrame(rows)
    annual = q.groupby("hcpcs").agg(pl_2027=("payment_limit", "mean"), pay_asp_2027=("pay_asp", "mean"),
                                    buy_asp_2027=("buy_asp", "mean"), addon_2027=("addon", "mean")).reset_index()
    return annual, q


def admin_fee_table(con, conversion_factor: float) -> dict[str, float]:
    """PFS non-facility allowed per admin code, Ohio statewide locality. CY2026 RVUs/GPCI with the CY2027
    PROPOSED conversion factor (2027 RVUs not final at build time; labelled in the README)."""
    loc = A.load()["locality"]
    rows = con.sql(f"""
        select r.hcpcs, r.work_rvu, r.pe_rvu_nonfac, r.mp_rvu, g.pw_gpci, g.pe_gpci, g.mp_gpci
        from staging.stg_pfs_rvu r
        cross join (select * from staging.stg_pfs_gpci
                    where state_abbr = '{loc["state_abbr"]}' and locality = '{loc["locality"]}') g
    """).df()
    return {r.hcpcs: M.pfs_payment(r.work_rvu, r.pe_rvu_nonfac, r.mp_rvu, r.pw_gpci, r.pe_gpci, r.mp_gpci,
                                   conversion_factor) for r in rows.itertuples()}


# ---------------------------------------------------------------- drivers
@dataclass
class Drivers:
    """Every driver the economics need; defaults come from config/assumptions.yaml."""

    commercial_drug_markup_vs_asp: float
    commercial_admin_multiple_of_medicare: float
    commercial_patient_resp_share: float
    patient_collection_rate: float
    denial_writeoff_medicare: float
    denial_writeoff_commercial: float
    underpayment_commercial: float
    medicaid_drug_markup_vs_asp: float
    medicaid_admin_multiple_of_medicare: float
    ma_rate_vs_ffs: float
    coinsurance_collection_rate: float
    acquisition_spread_vs_asp: float
    lesser_of_acquisition_premium: float
    variable_cost_per_infusion: float
    ivs_recapture_share: float = 0.0
    ivs_dispensing_margin: float = 0.0
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, **overrides) -> Drivers:
        p = A.practice()
        sc = A.load()["scenarios"]
        fields = {k: p[k] for k in cls.__dataclass_fields__ if k in p}
        fields.update({k: sc[k]["value"] for k in ("ivs_recapture_share", "ivs_dispensing_margin")})
        fields.update({k: v for k, v in overrides.items() if k in cls.__dataclass_fields__})
        return cls(**fields)

    def collect(self, payer: str) -> float:
        """Share of the allowed amount the practice actually collects, per payer (net-revenue haircut)."""
        medicare = M.provider_collection_factor(self.coinsurance_collection_rate)  # 80% x 0.98 + 20% x coll.
        if payer == "medicare_ffs":
            return medicare * (1 - self.denial_writeoff_medicare)
        if payer == "medicare_adv":  # MA contracts assumed to mirror FFS incl. sequestration; MA prior-auth denials
            return medicare * self.ma_rate_vs_ffs * (1 - self.denial_writeoff_commercial)
        if payer == "commercial":
            patient_bad_debt = self.commercial_patient_resp_share * (1 - self.patient_collection_rate)
            return (1 - patient_bad_debt) * (1 - self.denial_writeoff_commercial) * (1 - self.underpayment_commercial)
        return 1 - self.denial_writeoff_commercial  # medicaid: no cost sharing for these drugs


def per_admin(drugs: pd.DataFrame, prices: pd.DataFrame, fees: dict, d: Drivers) -> pd.DataFrame:
    """Per-administration revenue, drug cost and contribution (before fixed costs) by drug and payer.

    Medicare/MA allowed = units x PL(on ASP t-2). Commercial/Medicaid allowed = units x lagged ASP x
    (1 + markup) (contracts reference the current CMS file). Drug cost = units x ASP(t) x (1 + spread
    [+ lesser-of premium]). Contribution = collected revenue - drug cost - variable cost.
    """
    e = drugs.merge(prices, on="hcpcs", how="inner").copy()

    def admin_allowed(row) -> float:
        if row.admin_family not in INFUSION_FAMILIES:
            return 0.0  # Botox: chemodenervation procedure, outside chair economics
        first, addon = INFUSION_FAMILIES[row.admin_family]
        units = M.infusion_addon_units(row.admin_hours) if addon else 0
        return fees[first] + units * (fees[addon] if addon else 0.0)

    e["admin_allowed_medicare"] = e.apply(admin_allowed, axis=1)
    premium = np.where(e["flag_lesser_of"], d.lesser_of_acquisition_premium, 0.0)
    u = e["units_per_admin"]
    e["acquisition_cost"] = u * e["buy_asp_2027"] * (1 + d.acquisition_spread_vs_asp + premium)
    e["variable_cost"] = np.where(e["admin_family"].isin(CHAIR_FAMILIES + ("injection",)), d.variable_cost_per_infusion, 0.0)
    allowed = {
        "medicare_ffs": (u * e["pl_2027"], e["admin_allowed_medicare"]),
        "medicare_adv": (u * e["pl_2027"], e["admin_allowed_medicare"]),
        "commercial": (u * e["pay_asp_2027"] * (1 + d.commercial_drug_markup_vs_asp),
                       e["admin_allowed_medicare"] * d.commercial_admin_multiple_of_medicare),
        "medicaid": (u * e["pay_asp_2027"] * (1 + d.medicaid_drug_markup_vs_asp),
                     e["admin_allowed_medicare"] * d.medicaid_admin_multiple_of_medicare),
    }
    for p, (drug_allowed, admin_allowed_p) in allowed.items():
        c = d.collect(p)
        e[f"acquisition_cost_{p}"] = e["acquisition_cost"]
        e[f"drug_revenue_{p}"] = drug_allowed * c
        e[f"admin_revenue_{p}"] = admin_allowed_p * c
        e[f"drug_margin_{p}"] = e[f"drug_revenue_{p}"] - e["acquisition_cost"]
        e[f"contribution_{p}"] = e[f"drug_margin_{p}"] + e[f"admin_revenue_{p}"] - e["variable_cost"]
    # White bagging: the payer's specialty pharmacy supplies the drug; the practice keeps the admin fee,
    # and the owned specialty pharmacy may recapture a dispensing margin on part of that volume.
    recapture = d.ivs_recapture_share * d.ivs_dispensing_margin
    e["recapture_rate"] = recapture
    e["contribution_commercial_whitebag"] = e["admin_revenue_commercial"] - e["variable_cost"] + recapture * e["acquisition_cost"]
    return e


# ---------------------------------------------------------------- mix and volume
def payer_shares(con, commercial: float | None = None, medicaid: float | None = None) -> dict[str, float]:
    """Patient shares by payer. Commercial/Medicaid are assumptions; Medicare is split FFS vs MA with
    Ohio's real Original-Medicare share (CMS Monthly Enrollment)."""
    p = A.practice()
    c = p["payer_mix_commercial"] if commercial is None else commercial
    m = p["payer_mix_medicaid"] if medicaid is None else medicaid
    ffs = con.sql("""select sum(original_medicare_benes) / sum(medicare_benes)
                     from marts.dim_county where state_abbr = 'OH'""").fetchall()[0][0]
    medicare = 1 - c - m
    return {"commercial": c, "medicaid": m, "medicare_ffs": medicare * ffs, "medicare_adv": medicare * (1 - ffs)}


def within_line_shares(con, drugs: pd.DataFrame, full_formulary: bool = False) -> pd.DataFrame:
    """Patient share of each HCPCS inside its service line.

    Molecule shares: national 2024 in-office Medicare beneficiaries billed by the line's specialty
    (rheumatologists for the rheum line, neurologists for neuro). Product split inside a multi-source
    molecule: Ohio's 2024 biosimilar share of in-office administrations (unsuppressed geography rows),
    placed on the biosimilars on the formulary (Inflectra, Truxima). Listed molecules only, unless
    full_formulary (adds non-listed chair molecules: Orencia, Simponi Aria, Actemra, ...).
    """
    rows = []
    for line, specialties in LINES.items():
        mols = LINE_MOLECULES[line] + (EXTRA_MOLECULES[line] if full_formulary else ())
        specs = ",".join(f"'{s}'" for s in specialties)
        mol_in = ",".join(f"'{m}'" for m in mols)
        m = con.sql(f"""
            select d.molecule, sum(f.benes) as benes
            from marts.fct_provider_drug_year f
            join marts.dim_drug d using (hcpcs) join marts.dim_provider p using (npi)
            where f.year = 2024 and f.place_of_service = 'O' and p.provider_type in ({specs})
              and d.molecule in ({mol_in}) and d.admin_family in ('mab_infusion', 'iv_infusion')
              and (d.formulary_listed or {str(full_formulary).lower()} or d.molecule = 'immune_globulin')
            group by 1 order by 1
        """).df()
        m["mol_share"] = m["benes"] / m["benes"].sum()
        for r in m.itertuples():
            rows += [dict(line=line, hcpcs=h, share=r.mol_share * s) for h, s in product_split(con, drugs, r.molecule, full_formulary)]
    return pd.DataFrame(rows)


def product_split(con, drugs: pd.DataFrame, molecule: str, full_formulary: bool) -> list[tuple[str, float]]:
    g = drugs[(drugs["molecule"] == molecule) & drugs["admin_family"].isin(CHAIR_FAMILIES)]
    if molecule == "immune_globulin":  # listed IVIG brands, split by national beneficiaries
        codes = g[g["formulary_listed"]]["hcpcs"].tolist() if not full_formulary else g["hcpcs"].tolist()
        w = con.sql(f"""select hcpcs, benes from marts.fct_national_drug_year where year = 2024 and place_of_service = 'O'
                        and hcpcs in ({",".join(f"'{c}'" for c in codes)}) order by 1""").df()
        return list(zip(w["hcpcs"], w["benes"] / w["benes"].sum(), strict=True))
    ref = g[g["product_type"] != "biosimilar"]["hcpcs"].tolist()
    bios = g[g["product_type"] == "biosimilar"]
    if not ref:
        return []
    if bios.empty:
        return [(ref[0], 1.0)]
    oh = con.sql(f"""
        select sum(case when d.product_type = 'biosimilar' then s.bene_day_services else 0 end) / sum(s.bene_day_services)
        from marts.fct_state_drug_2024 s join marts.dim_drug d using (hcpcs)
        where s.state_abbr = 'OH' and s.place_of_service = 'O' and d.molecule = '{molecule}'
    """).fetchall()[0][0] or 0.0
    listed_bio = bios[bios["formulary_listed"]]["hcpcs"].tolist()
    target = listed_bio[0] if listed_bio else None
    if target is None or oh == 0:
        return [(ref[0], 1.0)]
    return [(ref[0], 1 - oh), (target, oh)]


def mix_by_payer(con, drugs: pd.DataFrame, overrides: dict | None = None, full_formulary: bool = False) -> pd.DataFrame:
    """Patient share by payer x HCPCS: service-line weight (payer-specific assumption) x within-line share."""
    p = {**A.practice(), **(overrides or {})}
    w = within_line_shares(con, drugs, full_formulary)
    out = []
    for payer in PAYERS:
        neuro = p["neuro_share_medicare"] if payer.startswith("medicare") else p["neuro_share_commercial"]
        imm = (1 - neuro) * p["immunology_share_of_non_neuro"]
        line_w = {"neuro": neuro, "immunology": imm, "rheum": 1 - neuro - imm}
        out.append(w.assign(payer=payer, patient_share=w["share"] * w["line"].map(line_w)))
    return pd.concat(out, ignore_index=True)[["payer", "line", "hcpcs", "patient_share"]]


def demand_growth(drugs: pd.DataFrame, con=None) -> pd.Series:
    """2027 / 2024 national in-office volume per molecule from the backtested volume forecast
    (the forecast decision rule currently picks naive, so this is 1.0 unless the data change)."""
    f = pd.read_csv(OUTPUTS / "forecasts_annual_volume.csv")
    f = f[(f["metric"] == "administrations") & (f["year"] == 2027)].set_index("molecule")["forecast"]
    hist = _annual_2024(con)
    g = (f / hist.reindex(f.index)).replace([np.inf, -np.inf], np.nan)
    return drugs["molecule"].map(g).fillna(1.0).set_axis(drugs["hcpcs"])


def _annual_2024(con=None) -> pd.Series:
    con = con or connect()
    return con.sql("""select d.molecule, sum(n.bene_day_services) as a from marts.fct_national_drug_year n
                      join marts.dim_drug d using (hcpcs) where n.year = 2024 and n.place_of_service = 'O'
                      and d.admin_family <> 'procedure' group by 1""").df().set_index("molecule")["a"]


# ---------------------------------------------------------------- suite P&L
def fixed_costs(chairs: float, overrides: dict | None = None) -> dict[str, float]:
    p = {**A.practice(), **(overrides or {})}
    open_hours = p["operating_days"] * p["chair_hours_per_day"]
    rn = chairs / p["chairs_per_rn"] * open_hours * p["rn_hourly_wage"] * (1 + p["benefits_load"])
    return {"nursing": rn, "rent_equipment": chairs * p["rent_equipment_per_chair_year"],
            "site_staff": p["site_fixed_staff_per_year"], "total": rn + chairs * p["rent_equipment_per_chair_year"]
            + p["site_fixed_staff_per_year"]}


def suite_pnl(econ: pd.DataFrame, mix: pd.DataFrame, payers: dict[str, float], growth: pd.Series,
              panel: float, chairs: float, white_bag: dict[str, float] | None = None,
              overrides: dict | None = None) -> dict:
    """Demand-driven annual P&L. Patients x administrations/yr -> chair-hours; capacity is a check: if
    demand exceeds chair-hours, volume is capped and the unmet demand is reported."""
    p = {**A.practice(), **(overrides or {})}
    e = econ.set_index("hcpcs")
    m = mix.copy()
    m["patients"] = panel * m["payer"].map(payers) * m["patient_share"]
    m["admins"] = m["patients"] * m["hcpcs"].map(e["admins_per_patient_year"]) * m["hcpcs"].map(growth).fillna(1.0)
    m["chair_hours"] = m["admins"] * m["hcpcs"].map(e["chair_hours"])
    capacity = chairs * p["operating_days"] * p["chair_hours_per_day"]
    demand_hours = m["chair_hours"].sum()
    served = min(1.0, capacity / demand_hours) if demand_hours else 0.0
    m["admins"] *= served
    m["chair_hours"] *= served

    def per(metric: str) -> pd.Series:
        out = []
        for r in m.itertuples():
            col = f"{metric}_{r.payer}"
            v = e.at[r.hcpcs, col]
            if r.payer == "commercial" and white_bag and metric in ("contribution", "drug_revenue", "admin_revenue"):
                share = white_bag.get(r.hcpcs, 0.0)
                wb = {"contribution": e.at[r.hcpcs, "contribution_commercial_whitebag"], "drug_revenue": 0.0,
                      "admin_revenue": e.at[r.hcpcs, "admin_revenue_commercial"]}[metric]
                v = v * (1 - share) + wb * share
            out.append(v)
        return pd.Series(out, index=m.index)

    for metric in ("drug_revenue", "admin_revenue", "contribution"):
        m[metric] = m["admins"] * per(metric)
    wb_share = m.apply(lambda r: (white_bag or {}).get(r.hcpcs, 0.0) if r.payer == "commercial" else 0.0, axis=1)
    acq = pd.Series([e.at[r.hcpcs, f"acquisition_cost_{r.payer}"] for r in m.itertuples()], index=m.index)
    m["drug_cost"] = m["admins"] * acq * (1 - wb_share)
    m["variable_cost"] = m["admins"] * m["hcpcs"].map(e["variable_cost"])
    # Owned-pharmacy dispensing margin on white-bagged volume: its own P&L line so revenue - costs reconciles
    m["pharmacy_margin"] = m["admins"] * acq * wb_share * m["hcpcs"].map(e["recapture_rate"])
    fixed = fixed_costs(chairs, overrides)
    admins = m["admins"].sum()
    contribution = m["contribution"].sum()
    hours = m["chair_hours"].sum()
    contrib_per_hour = contribution / hours if hours else 0.0
    open_hours = p["operating_days"] * p["chair_hours_per_day"]
    added_chair_fixed = fixed_costs(chairs + 1, overrides)["total"] - fixed["total"]
    unmet_hours = max(0.0, demand_hours - capacity)
    return {
        "patients": float(m["patients"].sum()), "administrations": float(admins),
        "chair_hours_demand": float(demand_hours), "chair_hours_capacity": float(capacity),
        "utilization": float(hours / capacity), "demand_served": float(served),
        "drug_revenue": float(m["drug_revenue"].sum()), "admin_revenue": float(m["admin_revenue"].sum()),
        "drug_cost": float(m["drug_cost"].sum()), "variable_cost": float(m["variable_cost"].sum()),
        "pharmacy_margin": float(m["pharmacy_margin"].sum()),
        "contribution": float(contribution), "fixed_costs": fixed, "operating_margin": float(contribution - fixed["total"]),
        "contribution_per_admin": float(contribution / admins) if admins else 0.0,
        "contribution_per_chair_hour": float(contrib_per_hour),
        "added_chair_fixed_cost": float(added_chair_fixed),
        "added_chair_breakeven_utilization": float(added_chair_fixed / (contrib_per_hour * open_hours)) if contrib_per_hour else None,
        "added_chair_value": float(contrib_per_hour * min(unmet_hours, open_hours) - added_chair_fixed),
        "by_payer": m.groupby("payer")[["patients", "admins", "contribution", "drug_revenue"]].sum().round(2).to_dict(orient="index"),
        "detail": m,
    }


def white_bag_tiers(econ: pd.DataFrame) -> dict[str, float]:
    """Share of commercial infusions white-bagged, by acquisition cost per infusion (payers target the most
    expensive drugs first)."""
    t = A.load()["scenarios"]["white_bagging_by_cost_tier"]["value"]
    def tier(cost: float) -> float:
        return t["above_10k"] if cost > t["threshold_high"] else t["from_3k_to_10k"] if cost >= t["threshold_low"] else t["below_3k"]
    return {r.hcpcs: tier(r.acquisition_cost) for r in econ.itertuples()}


def build(con=None, overrides: dict | None = None, rules_year: int = 2027, full_formulary: bool = False,
          mfp: bool = False, white_bag: bool = False, mix_override: pd.DataFrame | None = None,
          chairs: float | None = None, panel: float | None = None, payer_override: dict | None = None,
          buy_over_pay: dict[str, float] | None = None) -> dict:
    """One call = one scenario: prices -> per-admin economics -> mix -> suite P&L."""
    con = con or connect()
    o = overrides or {}
    p = {**A.practice(), **o}
    drugs = drug_frame(con)
    path = load_price_path()
    scale = {}
    if mfp:  # Medicare pays 106% of MFP and the practice's net cost falls to MFP (effectuation refund)
        disc = A.value("policy", "mfp_discount_vs_asp")
        scale = {h: 1 - disc for h in drugs[drugs["ipay2028_selected"]]["hcpcs"]}
    annual, quarterly = plan_prices(drugs, path, rules_year, buy_over_pay=buy_over_pay)
    fees = admin_fee_table(con, A.value("policy", "cf_2027_proposed"))
    d = Drivers.from_yaml(**o)
    econ = per_admin(drugs, annual, fees, d)
    if scale:  # MFP applies to Medicare FFS and MA only; commercial keeps ASP-based terms
        annual_mfp, _ = plan_prices(drugs, path, rules_year, asp_scale=scale, buy_over_pay=buy_over_pay)
        econ_mfp = per_admin(drugs, annual_mfp, fees, d)
        for payer in ("medicare_ffs", "medicare_adv"):
            for col in ("acquisition_cost", "drug_revenue", "drug_margin", "contribution"):
                econ.loc[econ["hcpcs"].isin(scale), f"{col}_{payer}"] = econ_mfp.loc[econ_mfp["hcpcs"].isin(scale), f"{col}_{payer}"].values
            # contribution here already nets the MFP acquisition cost through econ_mfp
    payers = payer_override or payer_shares(con, p.get("payer_mix_commercial"), p.get("payer_mix_medicaid"))
    mix = mix_override if mix_override is not None else mix_by_payer(con, drugs, o, full_formulary)
    growth = demand_growth(drugs, con)
    wb = white_bag_tiers(econ) if white_bag else None
    pnl = suite_pnl(econ, mix, payers, growth, panel or p["panel_patients"], chairs or p["chairs"], wb, o)
    return {"drugs": drugs, "econ": econ, "mix": mix, "payers": payers, "pnl": pnl, "quarterly_prices": quarterly,
            "white_bag": wb, "growth": growth}
