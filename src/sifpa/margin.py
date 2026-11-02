"""Module 2: infusion margin drivers (2027 basis). `make margin` -> outputs/margin*.{json,csv},
outputs/lag_spread_by_drug.csv, outputs/biosimilar_decision.csv, outputs/tornado.json.

Answers: what one administration earns by drug and payer in 2027; how often and how badly the 2-quarter
ASP lag leaves Medicare payment below the current purchase price (dollar-weighted, after sequestration
and coinsurance); which biosimilar product wins for which payer, and whether that call survives the
product's own price-change history; and which assumptions move the suite's result most.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from sifpa import assumptions as A
from sifpa import engine as E
from sifpa import mechanics as M
from sifpa.paths import OUTPUTS

MULTISOURCE = ["infliximab", "rituximab", "tocilizumab", "natalizumab", "denosumab"]


def lag_history(con) -> pd.DataFrame:
    """Per drug-quarter: PL(t), ASP(t) (read two files later), national in-office allowed $ that year."""
    return con.sql("""
        select f.hcpcs, d.molecule, d.product_type, f.payment_quarter, f.quarter_start, f.payment_limit,
               f.asp_current, f.asp_basis, f.lag_spread_pct, coalesce(n.allowed_amt, 0) as allowed_year
        from marts.fct_asp_quarter f join marts.dim_drug d using (hcpcs)
        left join marts.fct_national_drug_year n
          on n.hcpcs = f.hcpcs and n.year = year(f.quarter_start) and n.place_of_service = 'O'
        where f.asp_current is not null
    """).df()


def underwater(hist: pd.DataFrame) -> dict:
    """Is Medicare payment below the purchase price? Three definitions, unweighted and $-weighted.
    raw: PL(t) < ASP(t); after sequestration: 0.984 x PL < ASP; after sequestration and coinsurance
    collection at the assumed rate: collect x PL < ASP. Weight = that HCPCS's national in-office allowed $."""
    coll = A.practice()["coinsurance_collection_rate"]
    defs = {"raw": 1.0, "after_sequestration": M.provider_collection_factor(1.0),
            "after_sequestration_and_coinsurance": M.provider_collection_factor(coll)}
    out = {}
    for name, f in defs.items():
        uw = (hist["payment_limit"] * f < hist["asp_current"]).astype(float)
        w = hist["allowed_year"]
        out[name] = {"share_drug_quarters": round(float(uw.mean()), 4),
                     "dollar_weighted_share": round(float((uw * w).sum() / w.sum()), 4) if w.sum() else None}
    out["factors"] = {k: round(v, 5) for k, v in defs.items()}
    return out


def lag_spread_summary(hist: pd.DataFrame) -> pd.DataFrame:
    """Per drug: lag spread distribution and the realised 2-quarter ASP change (ASP(t)/ASP(t-2)) over the
    last 12 quarters: the price risk a buy-and-bill practice carries for that product."""
    h = hist.sort_values(["hcpcs", "quarter_start"]).copy()
    h["two_q_change"] = h["asp_current"] / h["asp_basis"]
    rows = []
    for code, g in h.groupby("hcpcs"):
        recent = g.tail(12)
        rows.append({"hcpcs": code, "molecule": g["molecule"].iloc[0], "product_type": g["product_type"].iloc[0],
                     "quarters": len(g), "median_lag_pct_last8": g["lag_spread_pct"].tail(8).median(),
                     "min_lag_pct": g["lag_spread_pct"].min(), "max_lag_pct": g["lag_spread_pct"].max(),
                     "two_q_change_p10": recent["two_q_change"].quantile(0.10),
                     "two_q_change_p90": recent["two_q_change"].quantile(0.90)})
    return pd.DataFrame(rows)


def biosimilar_decision(base: dict, lag: pd.DataFrame) -> pd.DataFrame:
    """Product x payer drug margin per infusion for multi-source molecules, at base acquisition and with
    acquisition moved to the product's own p10/p90 realised 2-quarter price change. 'robust' = the best
    product for that payer is the same at both ends. Products with < 4 quarters of history are flagged."""
    econ = base["econ"]
    lagi = lag.set_index("hcpcs")
    rows = []
    for mol in MULTISOURCE:
        g = econ[(econ["molecule"] == mol)]
        if g["product_type"].eq("biosimilar").sum() == 0:
            continue
        for payer in E.PAYERS:
            margins = {}
            for r in g.itertuples():
                base_m = getattr(r, f"drug_margin_{payer}")
                lo_c = lagi["two_q_change_p10"].get(r.hcpcs, np.nan)
                hi_c = lagi["two_q_change_p90"].get(r.hcpcs, np.nan)
                acq = r.acquisition_cost
                # price fell more than expected (p10) -> cheaper purchase; rose (p90) -> dearer purchase
                m_lo = base_m + acq * (1 - lo_c) if not np.isnan(lo_c) else np.nan
                m_hi = base_m - acq * (hi_c - 1) if not np.isnan(hi_c) else np.nan
                margins[r.hcpcs] = (base_m, m_lo, m_hi)
                rows.append({"molecule": mol, "payer": payer, "hcpcs": r.hcpcs, "brand": r.brand,
                             "product_type": r.product_type, "listed": bool(r.formulary_listed),
                             "price_history_quarters": int(lagi["quarters"].get(r.hcpcs, 0)),
                             "insufficient_price_history": int(lagi["quarters"].get(r.hcpcs, 0)) < 4,
                             "drug_margin_base": round(base_m, 2),
                             "drug_margin_if_price_falls_p10": round(m_lo, 2) if not np.isnan(m_lo) else None,
                             "drug_margin_if_price_rises_p90": round(m_hi, 2) if not np.isnan(m_hi) else None})
            best = max(margins, key=lambda h: margins[h][0])
            ends_ok = all(not np.isnan(v[1]) and not np.isnan(v[2]) for v in margins.values())
            robust = ends_ok and best == max(margins, key=lambda h: margins[h][1]) == max(margins, key=lambda h: margins[h][2])
            for row in rows:
                if row["molecule"] == mol and row["payer"] == payer:
                    row["best_for_payer"] = row["hcpcs"] == best
                    row["decision_robust"] = robust
    return pd.DataFrame(rows)


def tornado(con, metric: str = "operating_margin") -> dict:
    """Suite operating margin with each ranged assumption at its low/high (one-at-a-time)."""
    base = E.build(con)["pnl"][metric]
    bars = []
    for section, key, _base, low, high in A.ranged():
        if section != "practice":
            continue
        lo = E.build(con, overrides={key: low})["pnl"][metric]
        hi = E.build(con, overrides={key: high})["pnl"][metric]
        bars.append({"driver": key, "low_value": low, "high_value": high, "at_low": round(lo), "at_high": round(hi),
                     "swing": round(abs(hi - lo))})
    bars.sort(key=lambda b: -b["swing"])
    return {"metric": metric, "base": round(base), "bars": bars,
            "n_ranged_assumptions": len([r for r in A.ranged() if r[0] == "practice"])}


def per_chair_hour(base: dict) -> list[dict]:
    """Contribution per chair-hour by drug and payer, for drugs in the plan mix (capacity-allocation view)."""
    e = base["econ"]
    in_mix = set(base["mix"]["hcpcs"])
    e = e[e["hcpcs"].isin(in_mix)].copy()
    for p in ("medicare_ffs", "commercial"):
        e[f"{p}_per_chair_hour"] = e[f"contribution_{p}"] / e["chair_hours"]
    keep = ["hcpcs", "molecule", "chair_hours", "contribution_medicare_ffs", "contribution_commercial",
            "medicare_ffs_per_chair_hour", "commercial_per_chair_hour"]
    return e.sort_values("medicare_ffs_per_chair_hour", ascending=False)[keep].round(2).to_dict(orient="records")


def main() -> None:
    con = E.connect()
    base = E.build(con)
    econ = base["econ"]
    cols = ["hcpcs", "molecule", "brand", "product_type", "admin_family", "formulary_listed", "units_per_admin",
            "dose_mg", "admins_per_patient_year", "pl_2027", "pay_asp_2027", "buy_asp_2027", "flag_lesser_of",
            "asp_estimated", "admin_hours", "chair_hours", "admin_allowed_medicare", "acquisition_cost", "variable_cost"]
    cols += [f"{m}_{p}" for p in E.PAYERS for m in ("drug_revenue", "admin_revenue", "drug_margin", "contribution")]
    econ[cols].round(4).to_csv(OUTPUTS / "margin_per_admin.csv", index=False)

    hist = lag_history(con)
    lag = lag_spread_summary(hist)
    lag.round(4).to_csv(OUTPUTS / "lag_spread_by_drug.csv", index=False)
    dec = biosimilar_decision(base, lag)
    dec.to_csv(OUTPUTS / "biosimilar_decision.csv", index=False)
    torn = tornado(con)

    d = base["pnl"]["detail"]
    med = d[d["payer"] == "medicare_ffs"]
    med_drug_rev = (med["admins"] * med["hcpcs"].map(econ.set_index("hcpcs")["drug_revenue_medicare_ffs"])).sum()
    med_drug_margin = (med["admins"] * med["hcpcs"].map(econ.set_index("hcpcs")["drug_margin_medicare_ffs"])).sum()
    drv = E.Drivers.from_yaml()
    ff = E.build(con, full_formulary=True)
    ff_hi = E.build(con, full_formulary=True, overrides={"lesser_of_acquisition_premium":
                                                          A.load()["practice"]["lesser_of_acquisition_premium"]["high"]})
    summary = {
        "price_basis": "2027 average (payment on ASP t-2, purchase at ASP t)",
        "net_addon_after_sequestration_full_collection": round(M.net_addon_after_sequestration(), 5),
        "collection_factor_by_payer": {p: round(drv.collect(p), 4) for p in E.PAYERS},
        "medicare_drug_margin_pct_of_drug_revenue": round(float(med_drug_margin / med_drug_rev), 4),
        "contribution_per_admin_by_payer": {p: round(float(d[d["payer"] == p]["contribution"].sum()
                                                           / d[d["payer"] == p]["admins"].sum()), 2) for p in E.PAYERS},
        "ohio_admin_fee_96413_cf2027": round(E.admin_fee_table(con, A.value("policy", "cf_2027_proposed"))["96413"], 2),
        "underwater": underwater(hist),
        "median_lag_spread_pct_last8_reference_single_source": round(float(
            lag[lag["product_type"] != "biosimilar"]["median_lag_pct_last8"].median()), 4),
        "lesser_of_premium_effect_full_formulary": round(ff_hi["pnl"]["operating_margin"] - ff["pnl"]["operating_margin"]),
        "plan_mix_top": d.groupby("hcpcs")["admins"].sum().div(d["admins"].sum()).sort_values(ascending=False)
        .head(8).round(4).to_dict(),
        "contribution_per_chair_hour": per_chair_hour(base),
        "biosimilar_best_products": dec[dec["best_for_payer"]][["molecule", "payer", "hcpcs", "brand", "decision_robust"]]
        .to_dict(orient="records"),
        "n_drugs_priced": int(len(econ)),
    }
    (OUTPUTS / "margin.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (OUTPUTS / "tornado.json").write_text(json.dumps(torn, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("collection_factor_by_payer", "medicare_drug_margin_pct_of_drug_revenue",
                                              "contribution_per_admin_by_payer", "underwater",
                                              "lesser_of_premium_effect_full_formulary", "plan_mix_top")}, indent=1))
    print("tornado:", [(b["driver"], b["swing"]) for b in torn["bars"][:6]])
    print(pd.DataFrame(summary["biosimilar_best_products"]).to_string())


if __name__ == "__main__":
    main()
