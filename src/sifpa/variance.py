"""Budget vs actual: the month-end FP&A pack (ADR 0010).

Budget = the 2027 plan from engine.build(), per site (two illustrative sites), phased by month with
operating weekdays, at payer x drug grain. Actuals = a SYNTHETIC monthly table (seeded perturbation of
volume, payer/product mix and unit economics) that exists only to demonstrate the variance method.

Variance bridge per site x month (contribution), at item grain (item = payer|HCPCS):
  volume = (A_admins - B_admins) x B_contribution_per_admin
  mix    = sum_i (A_i - A_admins x B_i / B_admins) x B_unit_i
  rate   = sum_i A_i x (A_unit_i - B_unit_i)
  volume + mix + rate = A - B exactly (tested).

`make variance` -> exports/fact_plan_month.csv, exports/fact_actual_month_SYNTHETIC.csv,
exports/fact_fixed_month.csv, exports/dim_site.csv, exports/dim_item.csv,
outputs/variance_pack_SYNTHETIC.json, docs/VARIANCE_PACK_SYNTHETIC.md
"""

from __future__ import annotations

import calendar
import datetime as dt
import json

import numpy as np
import pandas as pd

from sifpa import assumptions as A
from sifpa import engine as E
from sifpa.paths import DOCS, EXPORTS, OUTPUTS

SEED = 2027
ACTUAL_MONTHS = 3  # SYNTHETIC actuals for Jan-Mar 2027 (an "as if" month-end close)
MEASURES = ["admins", "drug_revenue", "admin_revenue", "drug_cost", "variable_cost", "contribution"]


def weekdays(year: int = 2027) -> pd.Series:
    return pd.Series({m: sum(1 for d in range(1, calendar.monthrange(year, m)[1] + 1)
                             if dt.date(year, m, d).weekday() < 5) for m in range(1, 13)})


def budget() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    con = E.connect()
    sites = A.load()["sites"]["value"]
    wd = weekdays()
    rows, fixed, dim = [], [], []
    for i, (name, cfg) in enumerate(sites.items(), start=1):
        site_id = f"S{i}"
        r = E.build(con, chairs=cfg["chairs"], panel=cfg["panel_patients"],
                    overrides={"payer_mix_commercial": cfg["payer_mix_commercial"]})
        det = r["pnl"]["detail"]
        dim.append({"site_id": site_id, "site_name": name, "chairs": cfg["chairs"], "panel_patients": cfg["panel_patients"],
                    "payer_mix_commercial": cfg["payer_mix_commercial"], "utilization_plan": round(r["pnl"]["utilization"], 4)})
        for m, days in wd.items():
            share = days / wd.sum()
            month = dt.date(2027, m, 1)
            g = det[["payer", "hcpcs", *MEASURES]].copy()
            g[MEASURES] = g[MEASURES] * share
            rows.append(g.assign(site_id=site_id, month_start=month))
            fx = r["pnl"]["fixed_costs"]
            fixed.append({"site_id": site_id, "month_start": month, "nursing": fx["nursing"] / 12,
                          "rent_equipment": fx["rent_equipment"] / 12, "site_staff": fx["site_staff"] / 12,
                          "fixed_total": fx["total"] / 12})
    b = pd.concat(rows, ignore_index=True)
    b["item_key"] = b["payer"] + "|" + b["hcpcs"]
    return b, pd.DataFrame(fixed), pd.DataFrame(dim)


def synthetic_actuals(b: pd.DataFrame) -> pd.DataFrame:
    """SYNTHETIC: seeded perturbation of the budget for Jan-Mar 2027. Volume per site-month +-8%, an
    infliximab shift toward the listed biosimilar, a commercial-payer shift, collected revenue +-0.5% per item."""
    rng = np.random.default_rng(SEED)
    months = sorted(b["month_start"].unique())[:ACTUAL_MONTHS]
    a = b[b["month_start"].isin(months)].copy()
    # draw in sorted key order so the SYNTHETIC actuals do not depend on row order
    vol = {(s, m): rng.normal(1.0, 0.08) for s in sorted(a["site_id"].unique()) for m in months}
    a["admins_factor"] = [vol[(s, m)] for s, m in zip(a["site_id"], a["month_start"], strict=True)]
    a.loc[a["payer"] == "commercial", "admins_factor"] *= 0.94  # payer shift away from commercial
    a.loc[a["hcpcs"] == "J1745", "admins_factor"] *= 0.85        # Remicade patients moving to Inflectra
    a.loc[a["hcpcs"] == "Q5103", "admins_factor"] *= 2.20
    # revenue is ~13x contribution, so a 0.5% revenue wobble is a ~6% contribution wobble
    unit = {k: rng.normal(1.0, 0.005) for k in sorted(a["item_key"].unique())}
    a["unit_factor"] = a["item_key"].map(unit)
    scale_cols = ["drug_revenue", "admin_revenue", "drug_cost", "variable_cost", "contribution"]
    a["admins"] *= a["admins_factor"]
    for c in scale_cols:
        a[c] *= a["admins_factor"]
    a["contribution"] = (a["drug_revenue"] + a["admin_revenue"]) * a["unit_factor"] - a["drug_cost"] - a["variable_cost"]
    a["drug_revenue"] *= a["unit_factor"]
    a["admin_revenue"] *= a["unit_factor"]
    return a.drop(columns=["admins_factor", "unit_factor"]).assign(data_label="SYNTHETIC")


def bridge(b: pd.DataFrame, a: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Volume / mix / rate bridge of contribution at item grain within each `keys` group."""
    out = []
    bm = b[b["month_start"].isin(a["month_start"].unique())]
    groups = bm.groupby(keys) if keys else [((), bm)]
    for k, bg in groups:
        k = k if isinstance(k, tuple) else (k,)
        ag = a[np.logical_and.reduce([a[c] == v for c, v in zip(keys, k, strict=True)])] if keys else a
        bi = bg.groupby("item_key")[["admins", "contribution"]].sum()
        ai = ag.groupby("item_key")[["admins", "contribution"]].sum().reindex(bi.index.union(ag["item_key"].unique()), fill_value=0)
        bi = bi.reindex(ai.index, fill_value=0)
        b_unit = (bi["contribution"] / bi["admins"]).fillna(0)
        a_unit = (ai["contribution"] / ai["admins"]).fillna(0)
        b_tot, a_tot = bi["admins"].sum(), ai["admins"].sum()
        volume = (a_tot - b_tot) * bi["contribution"].sum() / b_tot
        mix = float(((ai["admins"] - a_tot * bi["admins"] / b_tot) * b_unit).sum())
        rate = float((ai["admins"] * (a_unit - b_unit)).sum())
        row = dict(zip(keys, k, strict=True))
        row.update({"budget": bi["contribution"].sum(), "actual": ai["contribution"].sum(), "volume": volume,
                    "mix": mix, "rate": rate})
        row["variance"] = row["actual"] - row["budget"]
        out.append(row)
    return pd.DataFrame(out)


def main() -> None:
    b, fixed, sites = budget()
    a = synthetic_actuals(b)
    b.round(6).to_csv(EXPORTS / "fact_plan_month.csv", index=False)
    a.round(6).to_csv(EXPORTS / "fact_actual_month_SYNTHETIC.csv", index=False)
    fixed.round(2).to_csv(EXPORTS / "fact_fixed_month.csv", index=False)
    sites.to_csv(EXPORTS / "dim_site.csv", index=False)
    items = b[["item_key", "payer", "hcpcs"]].drop_duplicates().sort_values("item_key")
    items.to_csv(EXPORTS / "dim_item.csv", index=False)
    by_site_month = bridge(b, a, ["site_id", "month_start"])
    by_site = bridge(b, a, ["site_id"])
    latest = max(a["month_start"])
    pack = {"data_label": "SYNTHETIC actuals (method demo); budget = 2027 plan model",
            "months_closed": [str(m) for m in sorted(a["month_start"].unique())],
            "latest_month": str(latest),
            "budget_contribution_full_year": round(float(b["contribution"].sum())),
            "by_site_month": by_site_month.round(2).astype({"month_start": str}).to_dict(orient="records"),
            "by_site_ytd": by_site.round(2).to_dict(orient="records"),
            "identity_max_abs_error": float((by_site_month["volume"] + by_site_month["mix"] + by_site_month["rate"]
                                             - by_site_month["variance"]).abs().max())}
    (OUTPUTS / "variance_pack_SYNTHETIC.json").write_text(json.dumps(pack, indent=2, default=str) + "\n")
    lines = ["# Month-end variance pack (SYNTHETIC actuals)", "",
             "**SYNTHETIC DATA: method demo only.** Budget = the 2027 plan model (two illustrative sites); actuals are "
             "a seeded perturbation (`src/sifpa/variance.py`). No business conclusion is drawn from this page.", "",
             f"Months closed: {', '.join(pack['months_closed'])}. Contribution, year to date:", "",
             "| Site | Budget | Actual | Variance | Volume | Mix | Rate |", "|---|---|---|---|---|---|---|"]
    for r in by_site.itertuples():
        lines.append(f"| {r.site_id} | ${r.budget:,.0f} | ${r.actual:,.0f} | ${r.variance:,.0f} | ${r.volume:,.0f} | ${r.mix:,.0f} | ${r.rate:,.0f} |")
    lines += ["", "Volume = change in administrations at budget contribution per administration; mix = change in the "
              "payer x drug mix at budget unit contribution; rate = change in contribution per administration "
              "(prices, collections, drug cost). The three add to the total variance exactly."]
    (DOCS / "VARIANCE_PACK_SYNTHETIC.md").write_text("\n".join(lines) + "\n")
    print(by_site.round(0).to_string(), "\nidentity error", pack["identity_max_abs_error"])


if __name__ == "__main__":
    main()
