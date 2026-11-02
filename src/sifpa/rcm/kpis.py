"""SYNTHETIC RCM KPIs: run sql/rcm/*.sql on the synthetic 837/835 tables -> outputs/rcm_kpis_SYNTHETIC.json."""

from __future__ import annotations

import json

import duckdb

from sifpa.paths import OUTPUTS, ROOT, SYNTHETIC

SQL_DIR = ROOT / "sql" / "rcm"


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    d = SYNTHETIC / "rcm"
    con.sql(f"create view claims as select * from read_csv_auto('{d / 'claims_837_SYNTHETIC.csv'}')")
    con.sql(f"create view remits as select * from read_csv_auto('{d / 'remits_835_SYNTHETIC.csv'}')")
    return con


def compute() -> dict:
    con = connect()
    out: dict = {"data_label": "SYNTHETIC", "note": "Method demo on invented data; no business conclusion."}
    for path in sorted(SQL_DIR.glob("*.sql")):
        rows = con.sql(path.read_text()).fetchall()
        out[path.stem] = {r[0]: round(float(r[1]), 6) for r in rows} if len(rows[0]) == 2 else round(float(rows[0][0]), 6)
    return out


def main() -> None:
    out = compute()
    (OUTPUTS / "rcm_kpis_SYNTHETIC.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
