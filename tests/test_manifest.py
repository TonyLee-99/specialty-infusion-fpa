"""Every raw source in ADR 0002 was pulled, is non-empty, and the raw total respects the disk budget."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "asp_payment_limits", "pfs_rvu", "pfs_gpci", "places_county", "census_pep_county", "zcta_county",
    "medicare_enrollment_county", "partb_spending_annual", "partb_spending_quarterly", "geo_service",
    "provider_2024", "provider_service", "county_gazetteer", "cbsa_county", "hospitals",
}


def test_manifest_lists_every_source_with_rows_and_hash():
    manifest = json.loads((ROOT / "data_manifest.json").read_text())
    assert set(manifest) >= EXPECTED
    for name in EXPECTED:
        entry = manifest[name]
        assert entry["rows"] > 0, name
        assert len(entry["sha256"]) == 64, name
        assert entry["source_url"].startswith("http"), name


def test_raw_total_under_budget():
    manifest = json.loads((ROOT / "data_manifest.json").read_text())
    assert manifest["_total_raw_mb"] < 3000  # raw-data disk budget is 3 GB


def test_asp_history_is_40_quarters():
    import duckdb
    n = duckdb.sql(
        f"select count(distinct quarter) from '{ROOT}/tests/fixtures/raw/asp_payment_limits.parquet'"
    ).fetchall()[0][0]
    assert n == 40


def test_fixture_slice_is_small():
    size = sum(p.stat().st_size for p in (ROOT / "tests/fixtures/raw").glob("*.parquet"))
    assert size < 5e6
