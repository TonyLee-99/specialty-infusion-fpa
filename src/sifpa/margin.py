"""Module 2: infusion margin drivers. `make margin` -> outputs/margin*.{json,csv}, outputs/tornado.json.

Answers: what does one administration earn by drug and payer, how big is the 2-quarter ASP lag effect,
what does biosimilar conversion do to margin, and which assumptions move the answer most.
"""

from __future__ import annotations

import json

import pandas as pd

from sifpa import assumptions as A
from sifpa import engine as E
from sifpa import mechanics as M
from sifpa.paths import OUTPUTS

MULTISOURCE = ["infliximab", "rituximab", "tocilizumab", "natalizumab", "denosumab"]


def realization_ratio(con) -> dict:
    """In-office allowed per billed unit vs the year's mean quarterly PL (2024, allowed-weighted).

    By statute allowed = lesser of charge or PL, so the ratio 'should' be ~1. It is measured, not assumed,
    and enters the tornado as a downside (ADR 0003 discusses the unexplained gap)."""
    df = con.sql("""
        with pl as (select hcpcs, avg(payment_limit) as pl from marts.fct_asp_quarter
                    where year(quarter_start) = 2024 group by 1)
        select n.hcpcs, n.allowed_amt, n.avg_allowed / pl.pl as ratio
        from marts.fct_national_drug_year n join pl using (hcpcs)
        where n.year = 2024 and n.place_of_service = 'O' and n.services > 0
    """).df()
    weighted = float((df["ratio"] * df["allowed_amt"]).sum() / df["allowed_amt"].sum())
    return {"allowed_weighted_ratio_2024": round(weighted, 4), "median_ratio_2024": round(float(df["ratio"].median()), 4),
            "n_codes": int(len(df))}


def lag_spread_summary(con) -> pd.DataFrame:
    """Lag spread = PL(t) - ASP(t) per unit, % of current ASP. Uses only quarters where ASP(t) is known
    (published two quarters later), so the last observable payment quarter is 2026Q2."""
    return con.sql("""
        select f.hcpcs, d.molecule, d.product_type, count(*) as quarters,
               median(f.lag_spread_pct) filter (where f.quarter_start >= date '2024-07-01') as median_lag_pct_last8,
               median(f.lag_spread_pct) as median_lag_pct_all,
               min(f.lag_spread_pct) as min_lag_pct, max(f.lag_spread_pct) as max_lag_pct,
               avg(case when f.lag_spread_pct < 0 then 1.0 else 0.0 end) as share_quarters_underwater
        from marts.fct_asp_quarter f join marts.dim_drug d using (hcpcs)
        where f.lag_spread_pct is not null
        group by all order by d.molecule, f.hcpcs
    """).df()


def biosimilar_conversion(econ: pd.DataFrame, con, payers: dict[str, float]) -> dict:
    """Per multi-source molecule: per-administration drug margin by product and payer, the switch delta
    from the reference to the biosimilar with the best payer-mix-weighted margin, and the hit when the
    IRA +8% add-on reverts to +6% for existing biosimilars after 2027-09-30."""
    out = {}
    econ = econ.copy()
    econ["drug_margin_blended"] = sum(w * econ[f"drug_margin_{p}"] for p, w in payers.items() if p != "ohio_ffs_share")
    for mol in MULTISOURCE:
        g = econ[econ["molecule"] == mol]
        ref = g[g["product_type"] == "reference"]
        bios = g[g["product_type"] == "biosimilar"]
        if ref.empty or bios.empty:
            continue
        ref = ref.iloc[0]
        best = bios.sort_values("drug_margin_blended", ascending=False).iloc[0]
        products = [
            {"hcpcs": r.hcpcs, "brand": r.brand, "product_type": r.product_type,
             "payment_limit": round(r.payment_limit, 3), "asp": round(r.asp_basis, 3),
             "addon_8pct": bool(r.flag_addon_8pct),
             "medicare_drug_margin": round(r.drug_margin_medicare_ffs, 2),
             "commercial_drug_margin": round(r.drug_margin_commercial, 2),
             "blended_drug_margin": round(r.drug_margin_blended, 2),
             "asp_estimated": bool(r.asp_estimated),
             "acquisition_cost": round(r.acquisition_cost, 2)}
            for r in g.sort_values("acquisition_cost").itertuples()
        ]
        units = float(best.units_per_admin)
        addon_expiry_hit = units * 0.02 * float(best.ref_asp or ref.asp_basis) if best.flag_addon_8pct else 0.0
        collect = M.provider_collection_factor(A.practice()["coinsurance_collection_rate"])
        out[mol] = {
            "units_per_admin": round(units, 1),
            "dose_mg": round(float(best.dose_mg), 0),
            "reference": ref.hcpcs,
            "best_biosimilar": best.hcpcs,
            "switch_delta_medicare_per_admin": round(best.drug_margin_medicare_ffs - ref.drug_margin_medicare_ffs, 2),
            "switch_delta_commercial_per_admin": round(best.drug_margin_commercial - ref.drug_margin_commercial, 2),
            "switch_delta_blended_per_admin": round(best.drug_margin_blended - ref.drug_margin_blended, 2),
            "acquisition_saving_per_admin": round(ref.acquisition_cost - best.acquisition_cost, 2),
            "ira_addon_expiry_hit_per_admin": round(addon_expiry_hit * collect, 2),
            "products": products,
        }
    # Infliximab history: Medicare drug margin per administration by product, steady state vs realised
    hist = con.sql("""
        select payment_quarter, hcpcs, payment_limit, asp_basis, asp_current
        from marts.fct_asp_quarter where molecule = 'infliximab' order by quarter_start, hcpcs
    """).df()
    out["_infliximab_history"] = hist.round(4).to_dict(orient="records")
    return out


def tornado(con, drugs: pd.DataFrame, fees: dict, realization: float) -> dict:
    """Annual contribution of the illustrative suite with each ranged assumption at its low/high."""
    mix = E.molecule_mix(con)
    p = A.practice()

    def run(overrides: dict) -> float:
        d = E.Drivers.from_yaml(**{k: v for k, v in overrides.items() if k in E.Drivers.__dataclass_fields__})
        econ = E.per_admin_economics(drugs, fees, d)
        payers = E.payer_mix(con, {k: v for k, v in overrides.items() if k.startswith("payer_mix")})
        per = E.blended(econ, mix, payers, d.white_bagging_share_commercial)
        vol = {k: overrides.get(k, p[k]) for k in ("chairs", "operating_days", "chair_hours_per_day", "chair_utilization")}
        return E.practice_pnl(per, **vol)["contribution"]

    base = run({})
    bars = []
    for section, key, _base, low, high in A.ranged():
        if section != "practice":
            continue
        lo, hi = run({key: low}), run({key: high})
        bars.append({"driver": key, "low_value": low, "high_value": high,
                     "contribution_at_low": round(lo), "contribution_at_high": round(hi),
                     "swing": round(abs(hi - lo))})
    lo = run({"drug_realization_vs_pl": realization})
    bars.append({"driver": "drug_realization_vs_pl (measured 2024)", "low_value": realization, "high_value": 1.0,
                 "contribution_at_low": round(lo), "contribution_at_high": round(base), "swing": round(abs(base - lo))})
    bars.sort(key=lambda b: -b["swing"])
    return {"base_contribution": round(base), "bars": bars,
            "n_ranged_assumptions": len([r for r in A.ranged() if r[0] == "practice"])}


def per_chair_hour(econ: pd.DataFrame, mix: pd.DataFrame) -> list[dict]:
    """Which infusions earn the most per chair-hour (Medicare FFS vs commercial)? Reference and
    single-source infusion drugs only; this is the capacity-allocation view for a full suite."""
    e = econ[econ["admin_family"].isin(["mab_infusion", "iv_infusion"]) & (econ["product_type"] != "biosimilar")].copy()
    e["medicare_per_chair_hour"] = e["contribution_medicare_ffs"] / e["chair_hours"]
    e["commercial_per_chair_hour"] = e["contribution_commercial"] / e["chair_hours"]
    e = e.merge(mix[["hcpcs", "share"]].rename(columns={"share": "mix_share"}), on="hcpcs", how="left")
    e["mix_share"] = e["mix_share"].fillna(0.0)
    e = e.sort_values("medicare_per_chair_hour", ascending=False)
    keep = ["hcpcs", "molecule", "mix_share", "chair_hours", "contribution_medicare_ffs", "contribution_commercial",
            "medicare_per_chair_hour", "commercial_per_chair_hour"]
    return e[keep].round(2).to_dict(orient="records")


def main() -> None:
    con = E.connect()
    drugs = E.drug_table(con)
    quarter = drugs["payment_quarter"].iloc[0]
    fees = E.admin_fee_table(con, A.value("policy", "cf_2026"))
    d = E.Drivers.from_yaml()
    econ = E.per_admin_economics(drugs, fees, d)
    cols = ["hcpcs", "molecule", "brand", "product_type", "admin_family", "units_per_admin", "dose_mg",
            "payment_limit", "asp_basis", "asp_estimated", "addon_pct", "admin_hours", "chair_hours",
            "drug_allowed_medicare", "drug_collected_medicare", "acquisition_cost", "drug_margin_medicare_ffs",
            "admin_allowed_medicare", "admin_collected_medicare", "chair_cost", "contribution_medicare_ffs",
            "drug_margin_commercial", "contribution_commercial", "contribution_medicaid"]
    econ[cols].round(4).to_csv(OUTPUTS / "margin_per_admin.csv", index=False)

    mix = E.molecule_mix(con)
    payers = E.payer_mix(con)
    per = E.blended(econ, mix, payers)
    medicare_only = E.blended(econ, mix, {"medicare_ffs": 1.0})
    commercial_only = E.blended(econ, mix, {"commercial": 1.0})
    realization = realization_ratio(con)
    lag = lag_spread_summary(con)
    lag.round(4).to_csv(OUTPUTS / "lag_spread_by_drug.csv", index=False)
    conv = biosimilar_conversion(econ, con, payers)
    torn = tornado(con, drugs, fees, realization["allowed_weighted_ratio_2024"])
    fee_96413 = fees["96413"]

    summary = {
        "price_quarter": quarter,
        "net_addon_after_sequestration_full_collection": round(M.net_addon_after_sequestration(), 5),
        "ohio_admin_fee_96413": round(fee_96413, 2),
        "ohio_admin_fee_96415": round(fees["96415"], 2),
        "ohio_admin_fee_96365": round(fees["96365"], 2),
        "chair_cost_per_hour": round(d.chair_cost_per_hour(), 2),
        "payer_mix": {k: round(v, 4) for k, v in payers.items()},
        "blended_per_admin": {k: round(v, 2) for k, v in per.items()},
        "medicare_ffs_per_admin": {k: round(v, 2) for k, v in medicare_only.items()},
        "commercial_per_admin": {k: round(v, 2) for k, v in commercial_only.items()},
        "drug_margin_share_of_gross_margin": round(per["drug_margin"] / (per["drug_margin"] + per["admin_revenue"]), 4),
        "medicare_drug_margin_pct_of_drug_revenue": round(medicare_only["drug_margin"] / medicare_only["drug_revenue"], 4),
        "n_drugs_priced": int(len(econ)),
        "n_drugs_in_mix": int(len(mix)),
        "realization": realization,
        "median_lag_spread_pct_last8_reference_single_source": round(float(
            lag[lag["product_type"] != "biosimilar"]["median_lag_pct_last8"].median()), 4),
        "share_quarters_underwater_all_drugs": round(float(lag["share_quarters_underwater"].mean()), 4),
        "practice_mix_top": mix.sort_values("share", ascending=False).head(8).round(4).to_dict(orient="records"),
        "contribution_per_chair_hour": per_chair_hour(econ, mix),
    }
    (OUTPUTS / "margin.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUTPUTS / "biosimilar_conversion.json").write_text(json.dumps(conv, indent=2, default=float) + "\n")
    (OUTPUTS / "tornado.json").write_text(json.dumps(torn, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("blended_per_admin", "medicare_ffs_per_admin", "commercial_per_admin",
                                              "realization", "drug_margin_share_of_gross_margin")}, indent=1))
    print("tornado top:", torn["bars"][:4])


if __name__ == "__main__":
    main()
