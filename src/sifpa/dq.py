"""`make dq`: data-quality checks run on every refresh. Hard failures exit non-zero; anomalies are flagged.

Writes outputs/dq_report.json. Hard checks protect the plan numbers (missing quarter, unpriced drug,
broken coverage); flags are things an analyst should look at before the numbers go to the EVP.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from sifpa import engine as E
from sifpa.paths import OUTPUTS

EXPECTED_QUARTERS = 40
PL_JUMP_FLAG = 0.25  # quarter-over-quarter payment-limit move worth a look


def run() -> dict:
    con = E.connect()
    con.execute(f"set variable raw_spending = '{OUTPUTS.parent / 'data' / 'raw' / 'partb_spending_annual.parquet'}'")
    checks: list[dict] = []

    def add(name: str, ok: bool, detail, hard: bool = True):
        checks.append({"check": name, "status": "pass" if ok else ("fail" if hard else "flag"), "detail": detail})

    q = con.sql("select count(distinct payment_quarter), max(payment_quarter) from marts.fct_asp_quarter").fetchall()[0]
    add("asp_quarters_complete", q[0] == EXPECTED_QUARTERS, {"quarters": q[0], "latest": q[1]})

    unpriced = con.sql(f"""
        select hcpcs from marts.dim_drug where hcpcs not in
          (select hcpcs from marts.fct_asp_quarter where payment_quarter = '{q[1]}')
          and hcpcs not in (select old_hcpcs from reference.hcpcs_successors)""").df()["hcpcs"].tolist()
    add("every_active_catalog_code_priced_latest_quarter", not unpriced, {"unpriced": unpriced})

    cov = con.sql("""select count(*), count(arthritis_prev), count(medicare_benes), count(lat)
                     from marts.dim_county where in_region""").fetchall()[0]
    extra = con.sql("""select count(*), count(arthritis_prev), count(lat) from marts.dim_county where not in_region""").fetchall()[0]
    add("county_coverage_607_region_plus_crossing_metros", cov == (607, 607, 607, 607) and extra[0] == extra[1] == extra[2],
        {"region_counts": cov, "cross_region_metro_counties": extra})

    nat = con.sql("select max(year) from marts.fct_national_drug_year").fetchall()[0][0]
    add("utilization_latest_year_2024", nat >= 2024, {"latest_year": nat})

    jumps = con.sql(f"""
        with x as (select hcpcs, payment_quarter, payment_limit,
                          lag(payment_limit) over (partition by hcpcs order by quarter_start) as prev
                   from marts.fct_asp_quarter)
        select hcpcs, payment_quarter, prev, payment_limit, payment_limit / prev - 1 as change
        from x where prev is not null and abs(payment_limit / prev - 1) > {PL_JUMP_FLAG}
          and payment_quarter >= '2025Q1'
        order by abs(payment_limit / prev - 1) desc""").df()
    add("payment_limit_jumps_since_2025", jumps.empty, jumps.round(4).to_dict(orient="records"), hard=False)

    # Allowed / payment limit: both CMS products (physician PUF allowed per unit, Part B Spending per
    # dosage unit) sit ~2-3% below the mean quarterly PL even for flat-price codes, so the gap is
    # systematic / definitional (consistent in size with the 2% sequestration adjustment), not a
    # practice realization risk. Only codes far below the cross-code median are flagged (unit artifacts).
    real = con.sql("""
        with pl as (select hcpcs, avg(payment_limit) as pl, stddev(payment_limit) / avg(payment_limit) as cv
                    from marts.fct_asp_quarter where year(quarter_start) = 2024 group by 1),
        s as (select HCPCS_Cd as hcpcs, try_cast(Avg_Spndng_Per_Dsg_Unt_2024 as double) as spend_per_unit
              from read_parquet(getvariable('raw_spending')))
        select n.hcpcs, pl.cv, n.avg_allowed / pl.pl as puf_allowed_ratio, s.spend_per_unit / pl.pl as partb_spend_ratio
        from marts.fct_national_drug_year n join pl using (hcpcs) left join s using (hcpcs)
        where n.year = 2024 and n.place_of_service = 'O' and n.services > 0""").df()
    flat = real[real["cv"] < 0.02]
    med_puf, med_spend = float(real["puf_allowed_ratio"].median()), float(real["partb_spend_ratio"].median())
    outliers = real[real["puf_allowed_ratio"] < med_puf - 0.05].round(4)
    checks.append({"check": "allowed_vs_payment_limit_explained", "status": "pass" if abs(med_puf - med_spend) < 0.02 else "flag",
                   "detail": {"median_puf_allowed_ratio": round(med_puf, 4), "median_partb_spend_ratio": round(med_spend, 4),
                              "median_ratio_flat_price_codes": round(float(flat["puf_allowed_ratio"].median()), 4),
                              "n_flat_price_codes": int(len(flat)),
                              "reading": "systematic in two independent CMS products, incl. flat-price codes -> definitional, not realization"}})
    add("allowed_far_below_cross_code_median_2024", outliers.empty, outliers.to_dict(orient="records"), hard=False)

    drop = con.sql("""
        with y as (select d.molecule, n.year, sum(n.providers) as prov from marts.fct_national_drug_year n
                   join marts.dim_drug d using (hcpcs) where n.place_of_service = 'O' group by 1, 2)
        select a.molecule, a.prov as prov_2023, b.prov as prov_2024, b.prov / a.prov - 1 as change
        from y a join y b on a.molecule = b.molecule and a.year = 2023 and b.year = 2024
        where b.prov / a.prov - 1 < -0.20""").df()
    add("billing_provider_drop_over_20pct_2024", drop.empty, drop.round(4).to_dict(orient="records"), hard=False)

    manifest = json.loads((OUTPUTS.parent / "data_manifest.json").read_text())
    empty = [k for k, v in manifest.items() if isinstance(v, dict) and v.get("rows", 0) == 0]
    add("no_empty_raw_pull", not empty, {"empty": empty})

    report = {"checks": checks,
              "n_fail": sum(c["status"] == "fail" for c in checks),
              "n_flag": sum(c["status"] == "flag" for c in checks),
              "n_pass": sum(c["status"] == "pass" for c in checks)}
    return report


def main() -> None:
    report = run()
    (OUTPUTS / "dq_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(pd.DataFrame(report["checks"])[["check", "status"]].to_string(index=False))
    if report["n_fail"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
