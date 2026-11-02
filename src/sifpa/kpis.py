"""`make kpis`: run every SQL twin in sql/measures/ on DuckDB over exports/*.csv -> outputs/kpis.json.

These are the 'published' values of the DAX measures (ADR 0007). tests/test_tmdl.py re-runs them and
cross-checks several against the analysis outputs (margin.json, scenarios.json, benchmark.json, ...).
"""

from __future__ import annotations

import json

import duckdb

from sifpa.paths import EXPORTS, OUTPUTS, ROOT

SQL_DIR = ROOT / "sql" / "measures"


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    ids = ("hcpcs", "npi", "county_fips", "market_id")
    for p in sorted(EXPORTS.glob("*.csv")):
        # id columns are read as text so leading zeros (FIPS, NPI) survive
        header = p.open().readline().strip().split(",")
        types = ", ".join(f"'{c}': 'VARCHAR'" for c in ids if c in header)
        con.sql(f"create view {p.stem} as select * from read_csv_auto('{p}', header=true, types={{{types}}})")
    return con


def compute() -> dict[str, float]:
    con = connect()
    # rounded to 9 dp: parallel float sums differ in the last bits run to run
    return {p.stem: round(float(con.sql(p.read_text()).fetchall()[0][0]), 9) for p in sorted(SQL_DIR.glob("*.sql"))}


def main() -> None:
    out = compute()
    (OUTPUTS / "kpis.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
