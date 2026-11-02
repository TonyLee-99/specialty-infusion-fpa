"""Per-administration economics by drug and payer, and a driver-based practice P&L.

margin.py (Module 2), scenarios.py (Module 3) and the Excel workbook all use this one engine, so every
number about infusion economics comes from the same formulas (see docs/decisions/0003, 0006).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import duckdb
import pandas as pd

from sifpa import assumptions as A
from sifpa import mechanics as M
from sifpa.paths import WAREHOUSE

INFUSION_FAMILIES = {"mab_infusion": ("96413", "96415"), "iv_infusion": ("96365", "96366"), "injection": ("96372", None)}


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(WAREHOUSE), read_only=True)


def mg_per_unit(billing_unit: str) -> float:
    """'10 MG' -> 10.0; '1 UNIT' -> 1.0 (botulinum units are their own unit)."""
    m = re.match(r"([\d.]+)", str(billing_unit))
    return float(m.group(1)) if m else 1.0


def drug_table(con: duckdb.DuckDBPyConnection, quarter: str | None = None) -> pd.DataFrame:
    """One row per catalog HCPCS priced in `quarter` (default: latest), with the observed dose.

    Dose per administration is observed: units / beneficiary-day in 2024 national in-office Medicare
    data, converted to mg and pooled at molecule level so new biosimilar codes inherit their molecule's dose.
    """
    quarter = quarter or con.sql("select max(payment_quarter) from marts.fct_asp_quarter").fetchall()[0][0]
    df = con.sql(f"""
        select d.hcpcs, d.molecule, d.brand, d.product_type, d.reference_hcpcs, d.admin_family,
               d.therapeutic_area, d.ipay2028_selected, d.formulary_listed, d.billing_unit,
               p.payment_limit, p.asp_basis, p.addon_pct, p.ref_asp, p.flag_addon_8pct
        from marts.dim_drug d
        join reference.drug_catalog dc using (hcpcs)
        join marts.fct_asp_quarter p on p.hcpcs = d.hcpcs and p.payment_quarter = '{quarter}'
    """).df()
    # "lesser of"/AMP-priced rows and ambiguous-reference biosimilars have no implied ASP: fall back
    # to PL / (1 + add-on) and flag it (overstates acquisition cost slightly, i.e. conservative).
    df["asp_estimated"] = df["asp_basis"].isna()
    df["asp_basis"] = df["asp_basis"].fillna(df["payment_limit"] / (1 + df["addon_pct"]))
    df["mg_per_unit"] = df["billing_unit"].map(mg_per_unit)
    dose = con.sql("""
        select n.hcpcs, n.services, n.bene_day_services, n.benes, d.molecule, d.billing_unit
        from marts.fct_national_drug_year n join marts.dim_drug d using (hcpcs)
        where n.year = 2024 and n.place_of_service = 'O' and n.bene_day_services > 0
    """).df()
    dose["mg"] = dose["services"] * dose["billing_unit"].map(mg_per_unit)
    mol = dose.groupby("molecule").agg(mg=("mg", "sum"), admins=("bene_day_services", "sum"),
                                       benes=("benes", "sum")).reset_index()
    mol["dose_mg"] = mol["mg"] / mol["admins"]
    mol["admins_per_bene_year"] = mol["admins"] / mol["benes"]
    df = df.merge(mol[["molecule", "dose_mg", "admins_per_bene_year"]], on="molecule", how="left")
    df["units_per_admin"] = df["dose_mg"] / df["mg_per_unit"]
    df["payment_quarter"] = quarter
    return df


def admin_fee_table(con: duckdb.DuckDBPyConnection, conversion_factor: float) -> dict[str, float]:
    """PFS non-facility allowed per admin code in the plan locality (Ohio statewide)."""
    loc = A.load()["locality"]
    rows = con.sql(f"""
        select r.hcpcs, r.work_rvu, r.pe_rvu_nonfac, r.mp_rvu, g.pw_gpci, g.pe_gpci, g.mp_gpci
        from staging.stg_pfs_rvu r
        cross join (select * from staging.stg_pfs_gpci
                    where state_abbr = '{loc["state_abbr"]}' and locality = '{loc["locality"]}') g
    """).df()
    return {
        r.hcpcs: M.pfs_payment(r.work_rvu, r.pe_rvu_nonfac, r.mp_rvu, r.pw_gpci, r.pe_gpci, r.mp_gpci,
                               conversion_factor)
        for r in rows.itertuples()
    }


@dataclass
class Drivers:
    """Every driver the per-administration math needs; defaults come from config/assumptions.yaml."""

    coinsurance_collection_rate: float
    acquisition_spread_vs_asp: float
    commercial_drug_markup_vs_asp: float
    commercial_admin_multiple_of_medicare: float
    medicaid_drug_markup_vs_asp: float
    medicaid_admin_multiple_of_medicare: float
    ma_rate_vs_ffs: float
    rn_hourly_wage: float
    benefits_load: float
    chairs_per_rn: float
    overhead_per_chair_hour: float
    white_bagging_share_commercial: float = 0.0
    drug_realization_vs_pl: float = 1.0  # measured gap scenario (outputs/dq_report.json); 1.0 = statute

    @classmethod
    def from_yaml(cls, **overrides) -> Drivers:
        p = A.practice()
        fields = {k: p[k] for k in cls.__dataclass_fields__ if k in p}
        fields.update(overrides)
        return cls(**fields)

    def chair_cost_per_hour(self) -> float:
        return self.rn_hourly_wage * (1 + self.benefits_load) / self.chairs_per_rn + self.overhead_per_chair_hour


def per_admin_economics(drugs: pd.DataFrame, fees: dict[str, float], d: Drivers) -> pd.DataFrame:
    """Per-administration revenue, cost and contribution by drug for each payer.

    Medicare FFS: allowed = units x PL; collected = allowed x (0.8 x 0.98 + 0.2 x collection rate).
    Acquisition (steady state) = units x ASP x (1 + spread): what the practice pays if prices hold flat.
    Commercial / Medicaid: ASP-based contract with a markup (labelled assumptions).
    """
    out = drugs.copy()
    times = A.load()["infusion_time"]
    out["admin_hours"] = out["molecule"].map(lambda m: times[m]["admin_hours"])
    out["chair_hours"] = out["molecule"].map(lambda m: times[m]["chair_hours"])
    inj = out["admin_family"].eq("injection")
    out.loc[inj, ["admin_hours", "chair_hours"]] = [0.0, 0.5]  # e.g. ocrelizumab subcutaneous J2351

    def admin_allowed(row) -> float:
        if row.admin_family not in INFUSION_FAMILIES:
            return 0.0  # Botox: chemodenervation procedure, outside chair economics
        first, addon = INFUSION_FAMILIES[row.admin_family]
        units = M.infusion_addon_units(row.admin_hours) if addon else 0
        return fees[first] + units * (fees[addon] if addon else 0.0)

    out["admin_allowed_medicare"] = out.apply(admin_allowed, axis=1)
    collect = M.provider_collection_factor(d.coinsurance_collection_rate)
    units, asp = out["units_per_admin"], out["asp_basis"]
    out["acquisition_cost"] = units * asp * (1 + d.acquisition_spread_vs_asp)
    out["chair_cost"] = out["chair_hours"] * d.chair_cost_per_hour()

    # Medicare FFS (MA assumed to pay ma_rate_vs_ffs x FFS)
    out["drug_allowed_medicare"] = units * out["payment_limit"] * d.drug_realization_vs_pl
    out["drug_collected_medicare"] = out["drug_allowed_medicare"] * collect
    out["admin_collected_medicare"] = out["admin_allowed_medicare"] * collect
    for payer, drug_rev, admin_rev in (
        ("medicare_ffs", out["drug_collected_medicare"], out["admin_collected_medicare"]),
        ("medicare_adv", out["drug_collected_medicare"] * d.ma_rate_vs_ffs,
         out["admin_collected_medicare"] * d.ma_rate_vs_ffs),
        ("commercial", units * asp * (1 + d.commercial_drug_markup_vs_asp),
         out["admin_allowed_medicare"] * d.commercial_admin_multiple_of_medicare),
        ("medicaid", units * asp * (1 + d.medicaid_drug_markup_vs_asp),
         out["admin_allowed_medicare"] * d.medicaid_admin_multiple_of_medicare),
    ):
        out[f"drug_revenue_{payer}"] = drug_rev
        out[f"admin_revenue_{payer}"] = admin_rev
        out[f"drug_margin_{payer}"] = drug_rev - out["acquisition_cost"]
        out[f"contribution_{payer}"] = out[f"drug_margin_{payer}"] + admin_rev - out["chair_cost"]
    # White bagging: payer supplies the drug; the practice keeps only the admin fee minus chair cost.
    out["contribution_commercial_whitebag"] = out["admin_revenue_commercial"] - out["chair_cost"]
    return out


def payer_mix(con: duckdb.DuckDBPyConnection, overrides: dict | None = None) -> dict[str, float]:
    """Commercial and Medicaid shares are assumptions; Medicare is split FFS vs MA using the plan
    state's real Original-Medicare share (CMS Monthly Enrollment)."""
    p = {**A.practice(), **(overrides or {})}
    state = A.load()["locality"]["state_abbr"]
    ffs = con.sql(f"""select sum(original_medicare_benes) / sum(medicare_benes)
                      from marts.dim_county where state_abbr = '{state}'""").fetchall()[0][0]
    medicare = 1 - p["payer_mix_commercial"] - p["payer_mix_medicaid"]
    return {"commercial": p["payer_mix_commercial"], "medicaid": p["payer_mix_medicaid"],
            "medicare_ffs": medicare * ffs, "medicare_adv": medicare * (1 - ffs), "ohio_ffs_share": ffs}


SPECIALTIES = ("Rheumatology", "Neurology", "Gastroenterology", "Allergy/ Immunology")  # CMS spelling has a space


def molecule_mix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Chair-drug mix of a regional inflammatory-disease practice: share of 2024 in-office Medicare administrations by
    HCPCS, billed by rheumatology / neurology / GI / allergy-immunology providers in the 7-state region.

    Infusions only (injections and Botox do not occupy an infusion chair). Provider rows < 11
    beneficiaries are suppressed by CMS, so small codes drop out and shares renormalise.
    """
    specs = ",".join(f"'{s}'" for s in SPECIALTIES)
    return con.sql(f"""
        select f.hcpcs, sum(f.bene_day_services) as admins,
               sum(f.bene_day_services) / sum(sum(f.bene_day_services)) over () as share
        from marts.fct_provider_drug_year f
        join marts.dim_provider p using (npi)
        join marts.dim_drug d using (hcpcs)
        where f.year = 2024 and f.place_of_service = 'O' and p.in_region
          and p.provider_type in ({specs}) and d.admin_family in ('mab_infusion', 'iv_infusion')
        group by f.hcpcs
    """).df()


def blended(econ: pd.DataFrame, mix: pd.DataFrame, payers: dict[str, float],
            white_bagging_share: float = 0.0) -> dict[str, float]:
    """Payer- and drug-mix weighted economics per administration."""
    e = econ.merge(mix[["hcpcs", "share"]], on="hcpcs", how="inner")
    e["share"] = e["share"] / e["share"].sum()
    res: dict[str, float] = {}
    for metric in ("drug_revenue", "admin_revenue", "drug_margin", "contribution"):
        total = 0.0
        for payer, w in payers.items():
            if payer == "ohio_ffs_share":
                continue
            col = e[f"{metric}_{payer}"]
            if payer == "commercial" and white_bagging_share:
                wb = {"drug_revenue": 0.0 * col, "admin_revenue": e["admin_revenue_commercial"],
                      "drug_margin": 0.0 * col, "contribution": e["contribution_commercial_whitebag"]}[metric]
                col = col * (1 - white_bagging_share) + wb * white_bagging_share
            total += w * float((col * e["share"]).sum())
        res[metric] = total
    res["chair_hours"] = float((e["chair_hours"] * e["share"]).sum())
    res["chair_cost"] = float((e["chair_cost"] * e["share"]).sum())
    res["acquisition_cost"] = float((e["acquisition_cost"] * e["share"]).sum())
    return res


def practice_pnl(per_admin: dict[str, float], chairs: float, operating_days: float,
                 chair_hours_per_day: float, chair_utilization: float) -> dict[str, float]:
    """Annual infusion-suite P&L: volume = booked chair-hours / chair-hours per administration."""
    booked_hours = chairs * operating_days * chair_hours_per_day * chair_utilization
    admins = booked_hours / per_admin["chair_hours"]
    return {
        "administrations": admins,
        "drug_revenue": admins * per_admin["drug_revenue"],
        "admin_revenue": admins * per_admin["admin_revenue"],
        "drug_margin": admins * per_admin["drug_margin"],
        "chair_cost": admins * per_admin["chair_cost"],
        "contribution": admins * per_admin["contribution"],
    }
