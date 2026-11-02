# 0002. Data sources: what works today, and what was swapped out

Date: 2026-11-02. Status: accepted. I probed every endpoint by hand before designing the pipeline.

## Probe results (2026-11-02)

| Source | Endpoint / file | Years available | Size we pull | Finding |
|---|---|---|---|---|
| Medicare Physician & Other Practitioners, by Provider and Service | `data.cms.gov/data-api/v1/dataset/<uuid>/data?filter[HCPCS_Cd]=...` (one uuid per year, from `data.cms.gov/data.json`) | 2013-2024 (2024 published 2026-05-21) | ~1-9k rows per code-year; filtered by HCPCS only | Filtering works (`curl -g` needed for the brackets). `/data/stats` returns `found_rows`. Rows with <11 beneficiaries are **suppressed by CMS** (the row is absent) |
| Medicare Physician & Other Practitioners, by Provider | same API | 2013-2024 | ~50k rows (4 specialties, all US) | Has drug vs medical allowed split, beneficiary risk score, and zip |
| Medicare Physician & Other Practitioners, by Geography and Service | same API | 2013-2024 | national + 7 states, our codes only | National rows are not suppressed. `Place_Of_Srvc` O = office (buy-and-bill), F = facility |
| Medicare Part B Spending by Drug | same API (`f48ced88-...`) | 2020-2024 in one wide file | ~1k rows | All settings (office + hospital outpatient). Includes `Avg_DY24_ASP_Price` |
| Medicare Quarterly Part B Spending by Drug | same API (`5cb9fd56-...`) | 2025 (Q1-Q4) and 2026 (Q1) | ~2k rows | Only the latest release is in the catalog, so there is **no quarterly history** to forecast from. Used only as a 2025 out-of-sample check |
| CMS ASP payment limit files | `cms.gov/files/zip/<month>-<year>-...zip` (2021+); older quarters at `cms.gov/Medicare/.../McrPartBDrugAvgSalesPrice/Downloads/<year>-<Month>-ASP-Pricing-File.zip` | 2017Q1-2026Q4 used (40 quarters) | 50-200 KB each | CSV "section 508" version inside each zip. Oct-2026 notes include `8% of reference add-on applied`, `"lesser of" methodology applied`, `AMP-based payment limit`, `Inflation-adjusted coinsurance`. Pre-2021 links go through the CMS/AMA CPT license page. We keep only HCPCS Level II J/Q codes and commit no CPT descriptors |
| CMS ASP NDC-HCPCS crosswalk | same page | 2017-2026 | small | Used to map biosimilar Q-codes to molecules (long descriptions) |
| PFS Relative Value File + GPCI + locality | `cms.gov/files/zip/rvu26d-updated-08-26-2026.zip` (6 MB) | CY2026 D (Oct) release | 6 MB zip, 3 CSVs used | CY2026 CF non-QPP = **$33.4009**. Ohio = one statewide locality (15202-00): PW 1.000 / PE 0.913 / MP 1.008. 96413 non-facility RVUs: work 0.28, PE 3.64, MP 0.07 |
| CY2027 PFS | Federal Register 2026-14327 (proposed, July 16 2026) | proposed only | none | Proposed CF non-QPP **$32.8409** (-1.68%). The final rule is expected early Nov 2026 and was not out when this was built. The plan uses the proposed CF and labels it |
| CDC PLACES county | `data.cdc.gov/resource/i46a-9kgh.json` (2025 release, GIS-friendly) | 2025 release (BRFSS 2023 model-based) | ~600 rows | `arthritis_crudeprev` with 95% CI, total and 18+ population. Arthritis = all types (mostly OA). It is a weak proxy for inflammatory disease, so it is labelled as one |
| Census ACS API | `api.census.gov/data/2023/acs/acs5/...` | n/a | n/a | **Fails: returns a 302 to `missing_key.html`.** No API key on this machine. **Replaced by** Census PEP Vintage 2025 county age-sex file (`www2.census.gov/.../cc-est2025-agesex-all.csv`, 10 MB, no key) for population and 65+ |
| Medicare Monthly Enrollment | `data.cms.gov` API (`cf1be15c-...`), county level | 2013-2026-07 | ~600 rows | Total, Original Medicare and MA beneficiaries by county, so MA penetration and FFS share |
| Census ZCTA-county relationship 2020 | `www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt` | 2020 | 6.8 MB | Provider zip5 maps to county by the largest land-area share. A ZIP is not exactly a ZCTA; the caveat is documented |
| CMS IPAY 2028 selected drugs | `cms.gov/files/document/factsheet-medicare-negotiation-selected-drug-list-ipay-2028.pdf` | Jan 27 2026 | 1 PDF | Part B drugs selected: **Orencia (J0129), Entyvio (J3380), Cimzia (J0717), Botox (J0585)**. MFPs due by Nov 30 2026 (**not yet published**) and effective Jan 1 2028 |
| CMS biosimilar FAQ (IRA s.11403) | `cms.gov/files/document/biosimilar-faqs.pdf` | | | Qualifying biosimilars are paid ASP + **8% of reference ASP** for 5 years. Biosimilars already on ASP before 2022-09-30 started 2022-10-01, so **their +8% ends 2027-09-30** |

Added during the build (same probe discipline):

| Census Gazetteer 2025 counties | `www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_counties_national.zip` | 2025 | 0.1 MB | **Pipe-delimited** in 2025 (earlier years were tab-delimited). County internal points are used for distance to the Columbus site |
| OMB CBSA delineation 2023 | `www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx` | 2023 | 0.1 MB | County to metro/micro. Markets are scored at this grain (ADR 0005 / market module) |

Build-time findings: PLACES 2025 has **null arthritis estimates for KY and PA**, so the 2024 release
(`d3i6-k6z5`) fills those two states (`places_release` column). CMS spells the specialty
**"Allergy/ Immunology"** (with a space); the first pull missed it until this was fixed. Final raw footprint:
see `_total_raw_mb` in `data_manifest.json` (about 44 MB).

Not used: Medicaid SDUD (Medicaid, not Medicare; the NDC mapping adds work without changing the
decision) and Transparency-in-Coverage PUF (optional; dropped to keep depth on the core question).

## Disk
Every pull is a filtered API call or a small zip. Expected raw footprint is under 300 MB, well inside
the 3 GB budget. `df -h ~` showed 24 GB free at start.

## Consequences
- The forecastable series are **annual** in-office volume and spend (2013-2024, by HCPCS) and
  **quarterly** ASP payment limits (2017Q1-2026Q4). See ADR 0004.
- Every raw pull is written with a manifest (URL, rows, sha256, pulled_at) to `data/raw/manifest.json`.
