"""Module 3b: CY2027 plan scenarios for the illustrative 12-chair suite (ADRs 0006, 0009).

  base                 2027 prices on the lagged ASP path (payment on ASP(t-2), purchase at ASP(t)),
                       CY2027 proposed CF, IRA +8% ends 2027-09-30 for existing biosimilars (current law),
                       formulary-listed drug mix by payer, demand-driven volume, net-revenue haircuts.
  biosimilar_listed    infliximab and rituximab move to the target biosimilar share on the products
                       the formulary lists (Inflectra, Truxima).
  biosimilar_best      upper bound: each payer's patients get the product with the best drug margin for that
                       payer (payer formularies permitting).
  policy_2028          2028 run-rate at 2027 prices: IRA add-on back to +6% all year for existing
                       biosimilars, MFP for selected drugs, cost-tiered white bagging net of the owned specialty pharmacy
                       recapture. Each component is also run alone (bridge).
  *_full_formulary     the same base and 2028 shock with the non-listed rheum/neuro chair drugs the operator
                       could add (Orencia, Simponi Aria, Actemra, ...): this is where MFP exposure lives.

`make scenarios` -> outputs/scenarios.json, outputs/scenario_drug_inputs.csv, outputs/plan_detail.csv
"""

from __future__ import annotations

import json

import pandas as pd  # noqa: I001

from sifpa import assumptions as A
from sifpa import engine as E
from sifpa.paths import OUTPUTS

PUSH_MOLECULES = ["infliximab", "rituximab"]  # multi-source molecules on the operator's published list


def push_listed_mix(mix: pd.DataFrame, drugs: pd.DataFrame) -> pd.DataFrame:
    """Raise the biosimilar share of each listed multi-source molecule to the target, on the listed product."""
    target = A.load()["scenarios"]["biosimilar_push_target_share"]["value"]
    d = drugs.set_index("hcpcs")
    m = mix.copy()
    m["molecule"] = m["hcpcs"].map(d["molecule"])
    m["is_bio"] = m["hcpcs"].map(d["product_type"]).eq("biosimilar")
    for _key, g in m[m["molecule"].isin(PUSH_MOLECULES)].groupby(["payer", "molecule"]):
        total, bio = g["patient_share"].sum(), g.loc[g["is_bio"], "patient_share"].sum()
        move = max(0.0, target * total - bio)
        ref_idx, bio_idx = g.index[~g["is_bio"]], g.index[g["is_bio"]]
        if len(bio_idx) and m.loc[ref_idx, "patient_share"].sum() > 0:
            ref_total = m.loc[ref_idx, "patient_share"].sum()
            m.loc[ref_idx, "patient_share"] *= 1 - min(move, ref_total) / ref_total
            m.loc[bio_idx[0], "patient_share"] += min(move, ref_total)
    return m.drop(columns=["molecule", "is_bio"])


def best_product_mix(mix: pd.DataFrame, drugs: pd.DataFrame, econ: pd.DataFrame) -> pd.DataFrame:
    """Each payer's share of a multi-source molecule goes to the product with the highest drug margin for
    that payer (all marketed products of the molecule are eligible)."""
    d = drugs.set_index("hcpcs")
    e = econ.set_index("hcpcs")
    rows = []
    m = mix.assign(molecule=mix["hcpcs"].map(d["molecule"]))
    for (payer, mol), g in m.groupby(["payer", "molecule"]):
        cands = drugs[(drugs["molecule"] == mol) & drugs["admin_family"].isin(E.CHAIR_FAMILIES)]["hcpcs"]
        if mol in PUSH_MOLECULES + ["natalizumab"] and len(cands) > 1:
            best = max(cands, key=lambda h: e.at[h, f"drug_margin_{payer}"])
            rows.append({"payer": payer, "line": g["line"].iloc[0], "hcpcs": best, "patient_share": g["patient_share"].sum()})
        else:
            rows += g.drop(columns="molecule").to_dict(orient="records")
    return pd.DataFrame(rows)


def summarise(r: dict) -> dict:
    p = r["pnl"]
    keys = ["patients", "administrations", "utilization", "drug_revenue", "admin_revenue", "drug_cost",
            "variable_cost", "contribution", "operating_margin", "contribution_per_admin", "contribution_per_chair_hour",
            "added_chair_fixed_cost", "added_chair_breakeven_utilization", "added_chair_value"]
    out = {k: round(p[k], 4) if isinstance(p[k], float) and abs(p[k]) < 10 else round(p[k]) for k in keys}
    out["fixed_costs"] = {k: round(v) for k, v in p["fixed_costs"].items()}
    det = p["detail"]
    for payer in E.PAYERS:
        g = det[det["payer"] == payer]
        out[f"contribution_per_admin_{payer}"] = round(float(g["contribution"].sum() / g["admins"].sum()), 2)
    out["commercial_share_of_contribution"] = round(float(det[det["payer"] == "commercial"]["contribution"].sum()
                                                         / det["contribution"].sum()), 4)
    out["commercial_share_of_admins"] = round(float(det[det["payer"] == "commercial"]["admins"].sum()
                                                   / det["admins"].sum()), 4)
    return out


def run(con) -> dict:
    base = E.build(con)
    drugs, econ, mix = base["drugs"], base["econ"], base["mix"]
    res = {"base": base,
           "biosimilar_listed": E.build(con, mix_override=push_listed_mix(mix, drugs)),
           "biosimilar_best": E.build(con, mix_override=best_product_mix(mix, drugs, econ)),
           "policy_2028": E.build(con, rules_year=2028, mfp=True, white_bag=True),
           "base_full_formulary": E.build(con, full_formulary=True),
           "policy_2028_full_formulary": E.build(con, rules_year=2028, mfp=True, white_bag=True, full_formulary=True)}
    bridge_runs = {"ira_addon_expiry": E.build(con, rules_year=2028), "mfp": E.build(con, mfp=True),
                   "white_bagging_net_of_ivs": E.build(con, white_bag=True)}
    ff_mfp = E.build(con, mfp=True, full_formulary=True)
    b = base["pnl"]["contribution"]
    out = {
        "plan_year": 2027,
        "price_basis": "2027 average: payment on lagged ASP path, purchase at current-quarter ASP (outputs/price_path.csv)",
        "payer_patient_shares": {k: round(v, 4) for k, v in base["payers"].items()},
        "conversion_factor_2027_proposed": A.value("policy", "cf_2027_proposed"),
        "scenarios": {k: summarise(v) for k, v in res.items()},
        "policy_2028_bridge": {k: round(v["pnl"]["contribution"] - b) for k, v in bridge_runs.items()},
        "mfp_effect_full_formulary": round(ff_mfp["pnl"]["contribution"] - res["base_full_formulary"]["pnl"]["contribution"]),
        "mfp_selected_share_of_admins_full_formulary": round(float(
            ff_mfp["pnl"]["detail"].assign(sel=lambda x: x["hcpcs"].map(drugs.set_index("hcpcs")["ipay2028_selected"]))
            .query("sel")["admins"].sum() / ff_mfp["pnl"]["detail"]["admins"].sum()), 4),
        "white_bag_tiers": A.load()["scenarios"]["white_bagging_by_cost_tier"]["value"],
        "labels": {"rvu": "CY2026 RVUs/GPCI with CY2027 proposed CF (2027 RVUs not final)",
                   "policy_2028": "2027 prices held; 2028 rules applied (no 2028 price forecast)"},
    }
    out["policy_2028_operating_margin_by_ivs_recapture"] = {
        str(r): round(E.build(con, rules_year=2028, mfp=True, white_bag=True,
                              overrides={"ivs_recapture_share": r})["pnl"]["operating_margin"]) for r in (0.0, 0.25, 0.5)}
    # Growth arithmetic. Both are mechanical in this model (labelled as such in the memo): extra patients
    # add their contribution linearly while chairs are free, and the panel was sized for ~70% utilization,
    # so an extra chair adds only its fixed cost until demand exceeds capacity.
    more = E.build(con, panel=A.practice()["panel_patients"] + 100)
    out["value_of_100_more_patients"] = round(more["pnl"]["contribution"] - b)
    out["growth_labels"] = {"value_of_100_more_patients": "linear: 100 x contribution per patient (chairs free)",
                            "added_chair_value": "equals the chair's fixed cost while demand < capacity",
                            "panel_sizing": "panel_patients set so the base runs near 70% utilization (assumption)"}

    # Commercial markup at which suite operating margin is zero (operating margin is linear in the markup)
    m0, m1 = 0.0, A.practice()["commercial_drug_markup_vs_asp"]
    op0 = E.build(con, overrides={"commercial_drug_markup_vs_asp": m0})["pnl"]["operating_margin"]
    op1 = base["pnl"]["operating_margin"]
    be = m0 + (0 - op0) * (m1 - m0) / (op1 - op0)
    check = E.build(con, overrides={"commercial_drug_markup_vs_asp": be})["pnl"]["operating_margin"]
    out["breakeven_commercial_markup"] = round(be, 5)
    out["breakeven_check_operating_margin"] = round(check, 2)

    # Lag-drift scenario: instead of the forecast path, assume each drug's historical
    # median lag spread (last 8 quarters) persists, i.e. today's purchase price sits PL/(1 + lag) and
    # Medicare keeps paying on the older, lower ASP. Drugs with < 8 quarters of history keep the forecast path.
    lag = pd.read_csv(OUTPUTS / "lag_spread_by_drug.csv", dtype={"hcpcs": str})
    lag = lag[lag["quarters"] >= 8].set_index("hcpcs")["median_lag_pct_last8"].dropna()
    ann = econ.set_index("hcpcs")
    factor = {h: float(ann.at[h, "pl_2027"] / ann.at[h, "pay_asp_2027"] / (1 + lag[h])) for h in lag.index if h in ann.index}
    drift = E.build(con, buy_over_pay=factor)
    out["lag_drift_scenario"] = {
        "operating_margin": round(drift["pnl"]["operating_margin"]),
        "delta_vs_base": round(drift["pnl"]["operating_margin"] - base["pnl"]["operating_margin"]),
        "delta_by_drug": {h: round(v) for h, v in (
            (drift["pnl"]["detail"].groupby("hcpcs")["contribution"].sum()
             - base["pnl"]["detail"].groupby("hcpcs")["contribution"].sum()).sort_values().head(5).items())},
        "n_drugs_with_history": len(factor)}
    tbl = econ.merge(drugs[["hcpcs"]], on="hcpcs")[[
        "hcpcs", "molecule", "brand", "product_type", "reference_hcpcs", "admin_family", "formulary_listed",
        "ipay2028_selected", "flag_lesser_of", "flag_addon_8pct", "ira_existing", "asp_estimated", "units_per_admin",
        "admins_per_patient_year", "admin_hours", "chair_hours", "pl_2027", "pay_asp_2027", "buy_asp_2027", "addon_2027",
        "admin_allowed_medicare", "acquisition_cost"]]
    pl28, _ = E.plan_prices(drugs, E.load_price_path(), 2028)
    tbl = tbl.merge(pl28[["hcpcs", "pl_2027"]].rename(columns={"pl_2027": "pl_2028_rules"}), on="hcpcs")
    tbl.round(6).to_csv(OUTPUTS / "scenario_drug_inputs.csv", index=False)
    mixes = (base["mix"].rename(columns={"patient_share": "share_base"})
             .merge(res["biosimilar_listed"]["mix"].rename(columns={"patient_share": "share_listed"}),
                    on=["payer", "line", "hcpcs"], how="outer").fillna(0.0))
    mixes.round(8).to_csv(OUTPUTS / "scenario_mix.csv", index=False)
    base["pnl"]["detail"].round(4).to_csv(OUTPUTS / "plan_detail.csv", index=False)
    (OUTPUTS / "scenarios.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


def main() -> None:
    out = run(E.connect())
    for k, s in out["scenarios"].items():
        print(f"{k:28s} contrib {s['contribution']:>10,} op {s['operating_margin']:>10,} util {s['utilization']:.3f} "
              f"per-admin {s['contribution_per_admin']}  med {s['contribution_per_admin_medicare_ffs']} "
              f"com {s['contribution_per_admin_commercial']} com-share {s['commercial_share_of_contribution']}")
    print("bridge", out["policy_2028_bridge"], "mfp ff", out["mfp_effect_full_formulary"],
          "+100 patients", out["value_of_100_more_patients"])
    b = out["scenarios"]["base"]
    print("added chair: fixed", b["added_chair_fixed_cost"], "breakeven util", b["added_chair_breakeven_utilization"],
          "value", b["added_chair_value"], "fixed", b["fixed_costs"])


if __name__ == "__main__":
    main()
