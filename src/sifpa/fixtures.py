"""`make fixtures`: a small, committed slice of the raw pulls so CI runs the same dbt models and tests
offline (Ohio providers, catalog codes, region counties). Keeps tests/fixtures/raw under ~5 MB."""

from __future__ import annotations

import duckdb
import pandas as pd

from sifpa.paths import FIXTURE_DIR, RAW, SEEDS

CODES = pd.concat([pd.read_csv(SEEDS / "drug_catalog.csv", dtype=str)["hcpcs"],
                   pd.read_csv(SEEDS / "admin_codes.csv", dtype=str)["hcpcs"]]).tolist()
STATES = pd.read_csv(SEEDS / "region_states.csv", dtype=str)


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("codes", pd.DataFrame({"hcpcs": CODES}))
    con.register("states", STATES)
    r = lambda name: f"'{RAW / name}.parquet'"  # noqa: E731
    slices = {
        "asp_payment_limits": f"select * from {r('asp_payment_limits')} where hcpcs in (select hcpcs from codes)",
        "provider_service": f"select * from {r('provider_service')} where Rndrng_Prvdr_State_Abrvtn = 'OH'",
        "provider_2024": f"select * from {r('provider_2024')} where Rndrng_Prvdr_State_Abrvtn = 'OH'",
        "geo_service": f"select * from {r('geo_service')} where HCPCS_Cd in (select hcpcs from codes)",
        "partb_spending_annual": f"select * from {r('partb_spending_annual')} where HCPCS_Cd in (select hcpcs from codes)",
        "partb_spending_quarterly": f"select * from {r('partb_spending_quarterly')} where HCPCS_Cd in (select hcpcs from codes)",
        "pfs_rvu": f"select * from {r('pfs_rvu')}",
        "pfs_gpci": f"select * from {r('pfs_gpci')}",
        "places_county": f"select * from {r('places_county')}",
        "census_pep_county": f"select * from {r('census_pep_county')} where lpad(STATE, 2, '0') in (select state_fips from states)",
        "zcta_county": f"select * from {r('zcta_county')} where left(GEOID_COUNTY_20, 2) in (select state_fips from states)",
        "medicare_enrollment_county": f"select * from {r('medicare_enrollment_county')} where MONTH = 'Year' "
                                      f"and YEAR = (select max(YEAR) from {r('medicare_enrollment_county')} where MONTH = 'Year')",
    }
    for name, sql in slices.items():
        out = FIXTURE_DIR / f"{name}.parquet"
        con.sql(sql).write_parquet(str(out), compression="zstd")
        n = con.sql(f"select count(*) from ({sql})").fetchall()[0][0]
        print(f"  {name}: {n:,} rows, {out.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
