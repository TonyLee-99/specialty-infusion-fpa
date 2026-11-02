"""Module 3b: CY2027 plan scenarios for the illustrative infusion suite (ADR 0006).

  base            2027 prices from the ASP forecast; CY2027 proposed PFS conversion factor; the IRA +8%
                  biosimilar add-on reverts to +6% for existing biosimilars from 2027Q4 (current law);
                  today's regional drug mix.
  biosimilar_push multi-source molecules reach the target biosimilar share, moved to the lowest-ASP
                  qualifying biosimilar (proxy for the payer-preferred product).
  policy_shock    2028 run-rate on the base: Medicare pays 106% of an assumed MFP for Orencia and Entyvio
                  (practice cost falls to MFP via effectuation), and payer white bagging takes a share of
                  commercial infusions.

The Excel workbook (excel_workbook.py) rebuilds the same numbers with live formulas from the inputs this
module writes; tests/test_excel.py checks they agree.

`make scenarios` -> outputs/scenarios.json, outputs/scenario_drug_inputs.csv
"""

from __future__ import annotations

import json

import pandas as pd

from sifpa import assumptions as A
from sifpa import engine as E
from sifpa import mechanics as M
from sifpa.paths import OUTPUTS

PUSH_MOLECULES = ["infliximab", "rituximab", "tocilizumab", "natalizumab"]
IRA_EXISTING_LAST_FIRST_QUARTER = "2022Q3"  # paid under ASP by 2022-09-30 -> window ends 2027-09-30


def addon_2027(row, first_quarter: dict[str, str]) -> float:
    """Average 2027 add-on % of reference ASP for a biosimilar (single-source/reference: 6% of own ASP)."""
    asp_addon = A.value("policy", "asp_addon_pct")
    ira = A.value("policy", "biosimilar_ira_addon_pct")
    if row.product_type != "biosimilar" or not row.flag_addon_8pct:
        return asp_addon
    if first_quarter[row.hcpcs] <= IRA_EXISTING_LAST_FIRST_QUARTER:
        return (3 * ira + asp_addon) / 4  # 8% for Q1-Q3, 6% for Q4 2027
    return ira


def drug_inputs_2027(con) -> pd.DataFrame:
    """Price table for 2027: forecast PL for reference/single-source codes with full history, latest PL
    held flat otherwise; biosimilar PL rebuilt from its ASP + the 2027 average add-on on reference ASP."""
    d = E.drug_table(con)
    fc = pd.read_csv(OUTPUTS / "forecasts_quarterly_asp.csv", dtype={"hcpcs": str})
    pl27 = fc.groupby("hcpcs")["forecast"].mean()
    first_q = con.sql("select hcpcs, min(payment_quarter) q from marts.fct_asp_quarter group by 1").df()
    first_quarter = dict(zip(first_q["hcpcs"], first_q["q"], strict=True))
    asp_addon = A.value("policy", "asp_addon_pct")

    d["price_source"] = d["hcpcs"].map(lambda h: "forecast_2027" if h in pl27.index else "held_flat_2026Q4")
    is_ref = d["product_type"] != "biosimilar"
    d.loc[is_ref, "asp_2027"] = d.loc[is_ref].apply(
        lambda r: pl27[r.hcpcs] / (1 + asp_addon) if r.hcpcs in pl27.index else r.asp_basis, axis=1)
    ref_asp = d.set_index("hcpcs")["asp_2027"]
    d.loc[~is_ref, "asp_2027"] = d.loc[~is_ref, "asp_basis"]
    d["ref_asp_2027"] = d["reference_hcpcs"].map(ref_asp)
    d["ira_existing"] = d["hcpcs"].map(lambda h: first_quarter[h] <= IRA_EXISTING_LAST_FIRST_QUARTER) & ~is_ref
    d["addon_2027"] = d.apply(lambda r: addon_2027(r, first_quarter), axis=1)
    bio_ok = ~is_ref & d["ref_asp_2027"].notna() & ~d["asp_estimated"]
    d["pl_2027"] = d["asp_2027"] * (1 + asp_addon)
    d.loc[bio_ok, "pl_2027"] = d.loc[bio_ok, "asp_2027"] + d.loc[bio_ok, "addon_2027"] * d.loc[bio_ok, "ref_asp_2027"]
    # Non-ASP-priced biosimilars (AMP-based / ambiguous reference): hold the published PL
    d.loc[~is_ref & ~bio_ok, "pl_2027"] = d.loc[~is_ref & ~bio_ok, "payment_limit"]
    d["mfp_selected"] = d["ipay2028_selected"].astype(bool)
    return d


def mixes(con, d: pd.DataFrame) -> pd.DataFrame:
    """Base mix (region, 2024) and the biosimilar-push mix per HCPCS."""
    target = A.load()["scenarios"]["biosimilar_push_target_share"]["value"]
    mix = E.molecule_mix(con)[["hcpcs", "share"]].rename(columns={"share": "mix_base"})
    m = d[["hcpcs", "molecule", "product_type", "asp_2027", "flag_addon_8pct"]].merge(mix, on="hcpcs", how="left")
    m["mix_base"] = m["mix_base"].fillna(0.0)
    m["mix_push"] = m["mix_base"]
    for mol in PUSH_MOLECULES:
        g = m[m["molecule"] == mol]
        total = g["mix_base"].sum()
        if total == 0:
            continue
        bios = g[(g["product_type"] == "biosimilar") & g["flag_addon_8pct"]]
        if bios.empty:
            bios = g[g["product_type"] == "biosimilar"]
        cheapest = bios.sort_values("asp_2027").index[0]
        bio_now = g[g["product_type"] == "biosimilar"]["mix_base"].sum()
        move = max(0.0, target * total - bio_now)  # only move reference volume, never reduce biosimilars
        ref_idx = g[g["product_type"] == "reference"].index
        ref_share = m.loc[ref_idx, "mix_base"].sum()
        if ref_share > 0:
            m.loc[ref_idx, "mix_push"] = m.loc[ref_idx, "mix_base"] * (1 - min(move, ref_share) / ref_share)
            m.loc[cheapest, "mix_push"] += min(move, ref_share)
    return m[["hcpcs", "mix_base", "mix_push"]]


def economics_2027(d: pd.DataFrame, fees: dict, drivers: E.Drivers) -> pd.DataFrame:
    priced = d.assign(payment_limit=d["pl_2027"], asp_basis=d["asp_2027"])
    return E.per_admin_economics(priced, fees, drivers)


def apply_mfp(econ: pd.DataFrame, drivers: E.Drivers) -> pd.DataFrame:
    """Medicare (FFS and MA) pays 106% of MFP; the practice's net cost falls to MFP after the
    manufacturer's effectuation refund, so the Medicare drug margin = units x MFP x (1.06 x collect - 1)."""
    disc = A.value("policy", "mfp_discount_vs_asp")
    collect = M.provider_collection_factor(drivers.coinsurance_collection_rate)
    e = econ.copy()
    sel = e["mfp_selected"]
    mfp = e.loc[sel, "asp_basis"] * (1 - disc)
    margin = e.loc[sel, "units_per_admin"] * mfp * ((1 + A.value("policy", "mfp_payment_pct")) * collect - 1)
    revenue = e.loc[sel, "units_per_admin"] * mfp * (1 + A.value("policy", "mfp_payment_pct")) * collect
    for payer, rate in (("medicare_ffs", 1.0), ("medicare_adv", drivers.ma_rate_vs_ffs)):
        e.loc[sel, f"drug_revenue_{payer}"] = revenue * rate
        e.loc[sel, f"drug_margin_{payer}"] = margin * rate
        e.loc[sel, f"contribution_{payer}"] = (margin * rate + e.loc[sel, f"admin_revenue_{payer}"]
                                               - e.loc[sel, "chair_cost"])
    return e


def run(con) -> dict:
    p = A.practice()
    d = drug_inputs_2027(con)
    fees = E.admin_fee_table(con, A.value("policy", "cf_2027_proposed"))
    drivers = E.Drivers.from_yaml()
    payers = E.payer_mix(con)
    m = mixes(con, d)
    econ = economics_2027(d, fees, drivers)
    econ_shock = apply_mfp(econ, drivers)
    wb = A.load()["scenarios"]["policy_shock_white_bagging"]["value"]
    vol = {k: p[k] for k in ("chairs", "operating_days", "chair_hours_per_day", "chair_utilization")}

    def scenario(econ_df, mix_col, white_bag):
        mix = m.rename(columns={mix_col: "share"})[["hcpcs", "share"]]
        mix = mix[mix["share"] > 0]
        per = E.blended(econ_df, mix, payers, white_bag)
        pnl = E.practice_pnl(per, **vol)
        medicare = E.blended(econ_df, mix, {"medicare_ffs": 1.0})
        commercial = E.blended(econ_df, mix, {"commercial": 1.0})
        return {"per_admin": {k: round(v, 4) for k, v in per.items()},
                "annual": {k: round(v) for k, v in pnl.items()},
                "contribution_per_chair": round(pnl["contribution"] / vol["chairs"]),
                "medicare_ffs_contribution_per_admin": round(medicare["contribution"], 2),
                "commercial_contribution_per_admin": round(commercial["contribution"], 2)}

    out = {
        "plan_year": 2027,
        "volume_drivers": vol,
        "payer_mix": {k: round(v, 4) for k, v in payers.items()},
        "conversion_factor_2027_proposed": A.value("policy", "cf_2027_proposed"),
        "scenarios": {
            "base": scenario(econ, "mix_base", 0.0),
            "biosimilar_push": scenario(econ, "mix_push", 0.0),
            "policy_shock": scenario(econ_shock, "mix_base", wb),
        },
    }
    # Policy-shock bridge: each component alone vs base
    out["policy_shock_bridge"] = {
        "mfp_orencia_entyvio": scenario(econ_shock, "mix_base", 0.0)["annual"]["contribution"]
        - out["scenarios"]["base"]["annual"]["contribution"],
        "white_bagging": scenario(econ, "mix_base", wb)["annual"]["contribution"]
        - out["scenarios"]["base"]["annual"]["contribution"],
    }
    # IRA +8% -> +6% expiry: the base already includes Q4 2027; full-year run-rate hit for 2028
    full8 = d.copy()
    full8["addon_2027"] = full8.apply(lambda r: A.value("policy", "asp_addon_pct") if r.ira_existing else r.addon_2027, axis=1)
    bio_ok = (full8["product_type"] == "biosimilar") & full8["ref_asp_2027"].notna() & ~full8["asp_estimated"]
    full8.loc[bio_ok, "pl_2027"] = full8.loc[bio_ok, "asp_2027"] + full8.loc[bio_ok, "addon_2027"] * full8.loc[bio_ok, "ref_asp_2027"]
    out["ira_addon_expiry_full_year_effect"] = scenario(economics_2027(full8, fees, drivers), "mix_base", 0.0)[
        "annual"]["contribution"] - out["scenarios"]["base"]["annual"]["contribution"]
    out["mfp_selected_share_of_base_mix"] = round(float(m.merge(d[["hcpcs", "mfp_selected"]], on="hcpcs")
                                                        .query("mfp_selected")["mix_base"].sum()), 4)
    out["n_drugs"] = int(len(d))
    out["n_drugs_forecast_priced"] = int((d["price_source"] == "forecast_2027").sum())

    keep = ["hcpcs", "molecule", "brand", "product_type", "reference_hcpcs", "admin_family", "units_per_admin",
            "payment_limit", "asp_basis", "asp_estimated", "price_source", "asp_2027", "ref_asp_2027",
            "flag_addon_8pct", "ira_existing", "addon_2027", "pl_2027", "mfp_selected"]
    table = d[keep].rename(columns={"payment_limit": "pl_2026q4", "asp_basis": "asp_2026q2"}).merge(m, on="hcpcs")
    table.round(6).to_csv(OUTPUTS / "scenario_drug_inputs.csv", index=False)
    (OUTPUTS / "scenarios.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


def main() -> None:
    out = run(E.connect())
    for name, s in out["scenarios"].items():
        print(name, s["annual"]["contribution"], s["per_admin"]["contribution"], s["annual"]["administrations"])
    print("bridge", out["policy_shock_bridge"], "ira full-year", out["ira_addon_expiry_full_year_effect"])


if __name__ == "__main__":
    main()
