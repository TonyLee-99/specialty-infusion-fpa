"""`make ingest`: every raw pull, written to data/raw/*.parquet, with data_manifest.json.

Run time ~5-10 min (several hundred small filtered API calls, 3 at a time, with 429 back-off).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pandas as pd

from sifpa.ingest import asp, cms_api, sources
from sifpa.paths import MANIFEST, RAW, SEEDS

PROVIDER_SERVICE = "Medicare Physician & Other Practitioners - by Provider and Service"
PROVIDER = "Medicare Physician & Other Practitioners - by Provider"
GEO_SERVICE = "Medicare Physician & Other Practitioners - by Geography and Service"
ENROLLMENT = "Medicare Monthly Enrollment"
SPENDING = "Medicare Part B Spending by Drug"
QUARTERLY_SPENDING = "Medicare Quarterly Part B Spending by Drug"

PROVIDER_SERVICE_YEARS = range(2019, 2025)
SPECIALTIES = ["Rheumatology", "Neurology", "Gastroenterology", "Allergy/ Immunology"]  # CMS spelling has a space
ADMIN_CODES = ["96365", "96366", "96413", "96415", "96372"]


def _drug_codes() -> list[str]:
    return pd.read_csv(SEEDS / "drug_catalog.csv", dtype=str)["hcpcs"].tolist()


def _states() -> pd.DataFrame:
    return pd.read_csv(SEEDS / "region_states.csv", dtype=str)


def _parallel(fn, jobs: list, workers: int = 3) -> pd.DataFrame:  # 3: stay under the CMS API rate limit
    with ThreadPoolExecutor(workers) as pool:
        frames = [f for f in pool.map(fn, jobs) if f is not None and len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def pull_provider_service() -> pd.DataFrame:
    """Drug codes 2019-2024 (all US providers) + admin codes for 2024 only (admin rows are large)."""
    uuids = cms_api.dataset_uuids(PROVIDER_SERVICE)
    jobs = [(y, c) for y in PROVIDER_SERVICE_YEARS for c in _drug_codes()]
    jobs += [(2024, c) for c in ADMIN_CODES]

    def one(job):
        year, code = job
        df = cms_api.fetch(uuids[year], {"HCPCS_Cd": code})
        return df.assign(year=year) if len(df) else None

    return _parallel(one, jobs)


def pull_provider_2024() -> pd.DataFrame:
    uuid = cms_api.dataset_uuids(PROVIDER)[2024]
    return _parallel(lambda s: cms_api.fetch(uuid, {"Rndrng_Prvdr_Type": s}).assign(year=2024), SPECIALTIES, 4)


def pull_geo_service() -> pd.DataFrame:
    """National rows for every HCPCS, 2013-2024 (national rows are not suppressed), plus state rows
    for the 7 region states (2024)."""
    uuids = cms_api.dataset_uuids(GEO_SERVICE)
    nat = _parallel(lambda y: cms_api.fetch(uuids[y], {"Rndrng_Prvdr_Geo_Lvl": "National"}).assign(year=y),
                    list(uuids))
    st = _parallel(lambda s: cms_api.fetch(uuids[2024], {"Rndrng_Prvdr_Geo_Desc": s}).assign(year=2024),
                   _states()["state_name"].tolist())
    return pd.concat([nat, st], ignore_index=True)


def pull_enrollment() -> pd.DataFrame:
    """County-level Medicare enrollment (total / Original Medicare / MA) for region states."""
    uuid = max(cms_api.dataset_uuids(ENROLLMENT).items())[1]
    df = _parallel(lambda s: cms_api.fetch(uuid, {"BENE_STATE_ABRVTN": s, "BENE_GEO_LVL": "County"}),
                   _states()["state_abbr"].tolist())
    keep = ["YEAR", "MONTH", "BENE_STATE_ABRVTN", "BENE_COUNTY_DESC", "BENE_FIPS_CD", "TOT_BENES",
            "ORGNL_MDCR_BENES", "MA_AND_OTH_BENES", "AGED_TOT_BENES"]
    return df[keep]


def pull_spending() -> dict[str, pd.DataFrame]:
    annual = cms_api.fetch(max(cms_api.dataset_uuids(SPENDING).items())[1])
    quarterly = cms_api.fetch(max(cms_api.dataset_uuids(QUARTERLY_SPENDING).items())[1])
    return {"partb_spending_annual": annual, "partb_spending_quarterly": quarterly}


def _write(name: str, df: pd.DataFrame, url: str, manifest: dict) -> None:
    path = RAW / f"{name}.parquet"
    df.astype(str).to_parquet(path, compression="zstd", index=False)
    manifest[name] = {
        "file": f"data/raw/{name}.parquet",
        "source_url": url,
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "pulled_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    # write the manifest after every source so an interrupted run (e.g. HTTP 429) never leaves
    # files on disk whose hashes the manifest does not describe
    manifest["_total_raw_mb"] = round(sum(p.stat().st_size for p in RAW.glob("*")) / 1e6, 1)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  {name}: {len(df):,} rows, {path.stat().st_size / 1e6:.1f} MB")


def main() -> None:
    free_gb = shutil.disk_usage(RAW).free / 1e9
    if free_gb < 8:
        raise SystemExit(f"Only {free_gb:.1f} GB free; stopping below 8 GB.")
    manifest: dict = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    cms = "https://data.cms.gov/data-api/v1/dataset/<uuid per year from data.json>/data"
    states = _states()["state_abbr"].tolist()

    asp_df, asp_urls = asp.pull()
    _write("asp_payment_limits", asp_df, asp.PAGE_URL + f" ({len(asp_urls)} quarterly zips)", manifest)
    for name, df in sources.pull_pfs().items():
        _write(name, df, sources.RVU_ZIP, manifest)
    _write("places_county", sources.pull_places(states), sources.PLACES_URL, manifest)
    _write("census_pep_county", sources.pull_pep(), sources.PEP_URL, manifest)
    _write("zcta_county", sources.pull_zcta(), sources.ZCTA_URL, manifest)
    _write("county_gazetteer", sources.pull_gazetteer(), sources.GAZ_URL, manifest)
    _write("cbsa_county", sources.pull_cbsa(), sources.CBSA_URL, manifest)
    _write("medicare_enrollment_county", pull_enrollment(), cms + f" [{ENROLLMENT}]", manifest)
    for name, df in pull_spending().items():
        _write(name, df, cms + " [Part B Spending by Drug]", manifest)
    _write("geo_service", pull_geo_service(), cms + f" [{GEO_SERVICE}]", manifest)
    _write("provider_2024", pull_provider_2024(), cms + f" [{PROVIDER}]", manifest)
    _write("provider_service", pull_provider_service(), cms + f" [{PROVIDER_SERVICE}]", manifest)

    manifest["_total_raw_mb"] = round(sum(p.stat().st_size for p in RAW.glob("*")) / 1e6, 1)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"raw total: {manifest['_total_raw_mb']} MB")


if __name__ == "__main__":
    main()
