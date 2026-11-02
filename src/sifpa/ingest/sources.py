"""Small non-CMS-API pulls: PFS RVU/GPCI, CDC PLACES, Census PEP, ZCTA-county relationship."""

from __future__ import annotations

import csv
import io
import zipfile

import pandas as pd

from sifpa.ingest.http import get

RVU_ZIP = "https://www.cms.gov/files/zip/rvu26d-updated-08-26-2026.zip"
PLACES_URL = "https://data.cdc.gov/resource/i46a-9kgh.json"  # 2025 release
# 2025 release has null arthritis estimates for KY and PA; the 2024 release fills those states.
PLACES_FALLBACK_URL = "https://data.cdc.gov/resource/d3i6-k6z5.json"
PEP_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/asrh/cc-est2025-agesex-all.csv"
GAZ_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_counties_national.zip"
CBSA_URL = "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx"
ZCTA_URL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt"

# Admin + E/M codes whose RVUs we need. CPT descriptors are intentionally dropped (AMA copyright).
PFS_CODES = ["96365", "96366", "96367", "96372", "96413", "96415", "96417", "99213", "99214", "99215", "99204", "99205"]


def _csv_rows(zf: zipfile.ZipFile, name_part: str) -> list[list[str]]:
    name = next(n for n in zf.namelist() if name_part in n and n.endswith(".csv"))
    return list(csv.reader(io.StringIO(zf.read(name).decode("latin-1"), newline="")))


def pull_pfs() -> dict[str, pd.DataFrame]:
    zf = zipfile.ZipFile(io.BytesIO(get(RVU_ZIP, timeout=300).content))
    rows = _csv_rows(zf, "PPRRVU2026_Oct_nonQPP")
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] == "HCPCS")
    rvu = []
    for r in rows[hdr_i + 1 :]:
        if r and r[0] in PFS_CODES and r[1] == "":
            # Column positions per the RVU26D layout (see header rows in the file).
            rvu.append({"hcpcs": r[0], "status": r[3], "work_rvu": r[5], "pe_rvu_nonfac": r[6],
                        "pe_rvu_fac": r[8], "mp_rvu": r[10], "conv_factor": r[25], "rvu_release": "RVU26D"})
    gpci_rows = _csv_rows(zf, "GPCI2026")
    g_hdr = next(i for i, r in enumerate(gpci_rows) if r and r[0].startswith("Medicare Administrative"))
    gpci = [
        {"mac": r[0], "state": r[1], "locality": r[2], "locality_name": r[3].strip(" *"),
         "pw_gpci": r[4], "pe_gpci": r[5], "mp_gpci": r[6]}
        for r in gpci_rows[g_hdr + 1 :] if len(r) >= 7 and r[1]
    ]
    return {"pfs_rvu": pd.DataFrame(rvu), "pfs_gpci": pd.DataFrame(gpci)}


def pull_places(states: list[str]) -> pd.DataFrame:
    where = "stateabbr in(" + ",".join(f"'{s}'" for s in states) + ")"
    cols = "stateabbr,statedesc,countyname,countyfips,totalpopulation,totalpop18plus," \
           "arthritis_crudeprev,arthritis_crude95ci,arthritis_adjprev"
    frames = []
    for release, url in (("2025", PLACES_URL), ("2024", PLACES_FALLBACK_URL)):
        rows = get(url, params={"$where": where, "$select": cols, "$limit": 5000}).json()
        frames.append(pd.DataFrame(rows).assign(places_release=release))
    return pd.concat(frames, ignore_index=True)


def pull_pep() -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(get(PEP_URL, timeout=300).content), dtype=str, encoding="latin-1")
    latest = df["YEAR"].astype(int).max()  # vintage 2025: YEAR 7 = July 1, 2025
    keep = ["STATE", "COUNTY", "STNAME", "CTYNAME", "YEAR", "POPESTIMATE", "AGE65PLUS_TOT", "AGE18PLUS_TOT"]
    return df.loc[df["YEAR"].astype(int) == latest, keep]


def pull_zcta() -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(get(ZCTA_URL, timeout=300).content), sep="|", dtype=str, encoding="latin-1")
    return df[["GEOID_ZCTA5_20", "GEOID_COUNTY_20", "NAMELSAD_COUNTY_20", "AREALAND_PART"]].dropna(
        subset=["GEOID_ZCTA5_20"])


def pull_gazetteer() -> pd.DataFrame:
    """County internal-point lat/long (Census Gazetteer 2025), for distance to the existing site."""
    zf = zipfile.ZipFile(io.BytesIO(get(GAZ_URL).content))
    name = next(n for n in zf.namelist() if n.endswith(".txt"))
    df = pd.read_csv(io.BytesIO(zf.read(name)), sep="|", dtype=str, encoding="latin-1")  # 2025 file is pipe-delimited
    df.columns = [c.strip() for c in df.columns]
    return df[["GEOID", "USPS", "NAME", "INTPTLAT", "INTPTLONG", "ALAND_SQMI"]]


def pull_cbsa() -> pd.DataFrame:
    """OMB 2023 CBSA delineation: county -> metro/micro area, so markets are scored at metro grain."""
    df = pd.read_excel(io.BytesIO(get(CBSA_URL).content), header=2, dtype=str)
    df = df.dropna(subset=["FIPS County Code"])
    df["county_fips"] = df["FIPS State Code"].str.zfill(2) + df["FIPS County Code"].str.zfill(3)
    df = df.rename(columns={"CBSA Code": "cbsa_code", "CBSA Title": "cbsa_title",
                            "Metropolitan/Micropolitan Statistical Area": "cbsa_type",
                            "Central/Outlying County": "central_outlying"})
    return df[["county_fips", "cbsa_code", "cbsa_title", "cbsa_type", "central_outlying"]]
