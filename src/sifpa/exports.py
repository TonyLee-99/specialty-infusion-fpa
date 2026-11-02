"""`make exports`: the star schema as CSVs in exports/, the files the Power BI semantic model loads.

Provider-level facts are limited to the 7-state region so the committed files stay small. No names.
Analysis outputs (margin, scenarios, forecasts, scorecard, market) are exported as facts too, so the
report and the README read the same numbers.
"""

from __future__ import annotations

import json
import shutil

import pandas as pd

from sifpa import engine as E  # noqa: F401  (connect() for warehouse tables)
from sifpa.paths import EXPORTS, OUTPUTS, SYNTHETIC

WAREHOUSE_TABLES = {
    "dim_drug": "select * from marts.dim_drug order by hcpcs",
    "dim_quarter": "select * from marts.dim_quarter order by quarter_start",
    "dim_date": "select * from marts.dim_date order by date",
    "fact_asp_quarter": """select payment_quarter, quarter_start, hcpcs, payment_limit, addon_pct, asp_basis,
                                  asp_current, lag_spread, lag_spread_pct, flag_addon_8pct
                           from marts.fct_asp_quarter order by hcpcs, quarter_start""",
    "fact_national_drug_year": """select year, hcpcs, place_of_service, providers, benes, services,
                                         bene_day_services, allowed_amt, payment_amt
                                  from marts.fct_national_drug_year order by year, hcpcs""",
    "dim_provider": """select npi, provider_type, state_abbr, county_fips, total_benes_2024, total_allowed_2024,
                              drug_allowed_2024, avg_risk_score_2024
                       from marts.dim_provider where in_region order by npi""",
    "fact_provider_drug_year": """select f.year, f.npi, f.hcpcs, f.place_of_service, f.hcpcs_role, f.benes,
                                         f.services, f.bene_day_services, f.allowed_amt
                                  from marts.fct_provider_drug_year f join marts.dim_provider p using (npi)
                                  where p.in_region and f.hcpcs_role = 'drug'
                                  order by f.year, f.npi, f.hcpcs""",
}


def main() -> None:
    con = E.connect()
    for name, sql in WAREHOUSE_TABLES.items():
        con.sql(sql).df().to_csv(EXPORTS / f"{name}.csv", index=False)

    # margin per administration by drug x payer + the plan's administration share per drug
    margin = pd.read_csv(OUTPUTS / "margin_per_admin.csv", dtype={"hcpcs": str})
    det = pd.read_csv(OUTPUTS / "plan_detail.csv", dtype={"hcpcs": str})
    mix = (det.groupby("hcpcs")["admins"].sum() / det["admins"].sum()).rename("mix_share")
    margin.merge(mix, left_on="hcpcs", right_index=True, how="left").fillna({"mix_share": 0.0}).to_csv(
        EXPORTS / "fact_margin_per_admin.csv", index=False)

    sc = json.loads((OUTPUTS / "scenarios.json").read_text())
    rows = [{"scenario": s, "metric": m, "value": v} for s, body in sc["scenarios"].items()
            for m, v in body.items() if isinstance(v, int | float)]
    pd.DataFrame(rows).to_csv(EXPORTS / "fact_scenarios.csv", index=False)

    shutil.copy(OUTPUTS / "price_path.csv", EXPORTS / "fact_price_path.csv")
    shutil.copy(OUTPUTS / "forecasts_annual_volume.csv", EXPORTS / "fact_forecast_annual_volume.csv")
    for src, dst in (("claims_837_SYNTHETIC.csv", "fact_rcm_claims_SYNTHETIC.csv"),
                     ("remits_835_SYNTHETIC.csv", "fact_rcm_remits_SYNTHETIC.csv")):
        shutil.copy(SYNTHETIC / "rcm" / src, EXPORTS / dst)
    sizes = {p.name: round(p.stat().st_size / 1e6, 2) for p in sorted(EXPORTS.glob("*.csv"))}
    print(json.dumps(sizes, indent=1), "total MB:", round(sum(sizes.values()), 1))


if __name__ == "__main__":
    main()
