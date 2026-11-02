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

    cov = con.sql("select count(*), count(arthritis_prev), count(medicare_benes), count(lat) from marts.dim_county").fetchall()[0]
    add("county_coverage_607", cov == (607, 607, 607, 607), {"counts": cov})

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

    real = con.sql("""
        with pl as (select hcpcs, avg(payment_limit) as pl from marts.fct_asp_quarter
                    where year(quarter_start) = 2024 group by 1)
        select n.hcpcs, n.avg_allowed / pl.pl as ratio, n.allowed_amt
        from marts.fct_national_drug_year n join pl using (hcpcs)
        where n.year = 2024 and n.place_of_service = 'O' and n.services > 0
          and n.avg_allowed / pl.pl < 0.90 order by ratio""").df()
    add("allowed_below_90pct_of_payment_limit_2024", real.empty, real.round(4).to_dict(orient="records"), hard=False)

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
