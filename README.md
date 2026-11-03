# specialty-infusion-fpa

**In-office infusion FP&A for a multi-site inflammatory-disease practice, built on public CMS data:** what
infusion really earns, how exposed it is to biosimilar, ASP and policy shifts, where growth should come from,
and how the plan becomes a monthly budget-vs-actual pack. It is written for the EVP of FP&A at a
regional inflammatory-disease practice. It uses public data only, and I have no affiliation with the operator it is modelled on.

> **Headline (2027 basis):** an illustrative 12-chair suite on a regional operator's published drug list makes
> **$2.73M** operating margin on 7,413 infusions. Medicare FFS contributes **$172** per infusion,
> because its drug margin is **1.6%** after sequestration, coinsurance bad debt and denials. The
> assumed commercial contract contributes **$946**, so commercial is 88% of contribution. The 2028
> risk is white bagging (-$566K), not Medicare negotiation ($0 on the listed drugs). Grow by patients
> (100 more add $222K), not chairs (one more costs $57K/yr at 67% utilization). Next site:
> Canton-Massillon, OH or Youngstown-Warren, OH (Northeast Ohio gaps; recruiting needed). Cleveland is well served (#21). Detroit-Warren-Dearborn, MI ranks first overall.

| Problem | What I built | Key results (real numbers, reproducible) |
|---|---|---|
| Next year's plan needs to know what infusion earns and how fragile it is | Buy-and-bill engine on the real 2-quarter lag (pay on ASP t-2, buy at ASP t), biosimilar add-on on *reference* ASP, net collection for every payer, demand-driven volume, fixed vs variable cost | Medicare FFS $172, MA $68, commercial $946 per infusion. Commercial markup range moves operating margin $15K to $6.13M |
| Policy and product shifts hit at different times | Product x payer biosimilar decision table; cost-tiered white bagging with owned-pharmacy recapture; 2028 run-rate bridge; Excel with 1,757 live formulas | Listed biosimilars $20K; best product per payer up to $237K (only 2/12 picks robust); 2028 -$580K |
| Growth and the monthly pack | Market-grain white-space ranking (cross-state metros whole, prescriber floor); budget by site/month + SYNTHETIC actuals with a volume/mix/rate bridge; sliceable Power BI model | Canton-Massillon, OH: rank 2 of 74. Site A Q1 variance (SYNTHETIC) $-68,232 = volume $-47,020 + mix $-20,296 + rate $-916 |

![Executive page of the scorecard](docs/img/scorecard_exec.png)

---

## Executive decision memo: CY2027 in-office infusion plan

**To:** EVP, Financial Planning & Analysis. **From:** Zhengtao (Tony) Li. **Date:** 2026-11-02.
**Basis:** public CMS / CDC / Census data, one price basis (2027: Medicare pays on the ASP of two quarters
earlier, the practice buys at the current ASP). Patients, payer mix, contracts and costs are labelled
assumptions for an illustrative 12-chair suite with a regional operator's published drug list. Read the $ per
infusion and the deltas; the totals are illustrations.

### Recommendation
1. **Budget the infusion line as a commercial-contract business.** The 2027 base case gives 7,413
   infusions for 1,700 patients (67% of chair capacity). Contribution is $3.77M; after $1.03M of
   fixed suite cost, operating margin is $2.73M. Medicare FFS contributes $172 per infusion: ASP+6% nets
   to 4.3% after sequestration, and after coinsurance bad debt and denials the Medicare drug margin is
   1.6% of drug revenue. MA contributes $68. The assumed commercial contract contributes $946,
   after patient bad debt, denials and underpayment (93.2% collected). Commercial is 47% of
   infusions and 88% of contribution.
2. **Decide biosimilars product by payer; don't push them across the board.** Moving infliximab and rituximab
   to 80% on the listed products (Inflectra, Truxima) changes operating margin by $20K.
   Giving each payer its best-margin product would add up to $237K. But only 2 of the 12
   payer-level picks in that scenario survive the products' own price swings over the last 12 quarters with
   enough price history. Robust Medicare picks: Riabni. Switch Medicare patients only where the pick is
   robust, and ask commercial payers to price biosimilars on reference-ASP terms before converting them.
3. **Contract for 2028 now; the exposure is white bagging, not drug negotiation.** The 2028 run-rate changes
   operating margin by -$580K. White bagging accounts for -$566K (tiered by drug cost, net of the owned specialty pharmacy
   recapture), and the end of the +8% add-on for -$13K. Medicare negotiation costs $0 on the listed drug
   list, because none of those drugs was selected. Adding Orencia to the formulary (selected drugs would be
   25% of infusions in a full-formulary book) changes this by only -$43, because the Medicare margin on it is
   about 1%. That conclusion depends on buying Orencia at WAC: at WAC+5% the MFP effect becomes $64K, and at
   the stress bound $899K (the MFP refund would then rescue an underwater drug). Priorities: site-of-care and white-bagging carve-outs in contracts; the owned specialty pharmacy in payer
   networks (each 25 points of recapture is worth $55K).
4. **Grow by patients, not chairs, until chairs fill.** Both growth numbers are model arithmetic, not
   findings: the panel was sized for about 70% utilization (67% in the base after forecast demand),
   so another chair adds only its
   $57K fixed cost (-$57K a year), and 100 more patients add $222K (linear, while chairs
   are free). Once demand exceeds capacity, an added chair breaks even at 12% utilization.
   - **New site.** Detroit-Warren-Dearborn, MI ranks first overall (63% of random weightings in the top 10) but leaves Ohio.
     The best Ohio markets outside the Columbus catchment are **Canton-Massillon, OH** (#2, 76%; 4.7
     relevant specialists per 100k and 0 Medicare-billing rheumatologists, so a site there means
     recruiting) and Youngstown-Warren, OH (#3).
   - Cleveland is not a gap market: rank 21, with 23.5 relevant specialists per 100k
     (78 rheumatologists).

### Risks
- **Commercial terms decide whether the suite makes money.** Operating margin is zero at a commercial
  drug markup of 7.9% over ASP (the plan assumes 20%). Across the documented range
  (8% to 35%), operating margin runs from $15K to $6.13M. Purchasing is next: an acquisition
  spread of -5% to +3% vs ASP moves it from $4.97M to $1.39M.
- **Price path and the lag.** 2027 prices follow the models picked on a decision window (MAPE 7.0% vs
  9.2% naive there). On the untouched test window, on the same 978 forecasts, naive was slightly
  better (4.8% vs 5.2%). Per-series DM tests at one quarter ahead found 1 series
  significantly better and 1 significantly worse of 16: no systematic edge. Both under-forecast
  (naive by 1.8%), because prices drift up. If each drug's historical lag spread persists instead,
  operating margin changes by -$335K; Ocrevus (-$130K) and Vyepti (-$100K) lead. In 30% of past
  drug-quarters (36% dollar-weighted), Medicare's collected payment fell below the price paid at the time.
  The path's 80% band covered 77% of test outcomes.
- **Orencia pricing.** Orencia's Medicare limit is set on WAC ("lesser of"), so the base buys at WAC. At
  WAC+5%, full-formulary operating margin falls from $2.96M to $2.61M. The stress bound (acquisition on
  the old ASP trend, 70% above WAC, not a credible purchase price) would take it to -$1.97M.
- **Data limits.** Medicare FFS only; MA claims are not public. The drug mix comes from what
  neurologists and rheumatologists bill in office nationally, and it under-represents hospital-based MS
  infusion. Provider-level biosimilar rates cannot be measured through CMS suppression, so adoption is
  benchmarked by state (infliximab 11.0% Ohio vs 14.1% US).

### What would change this recommendation
- Commercial biosimilar contracts priced on reference-ASP terms: biosimilar conversion becomes a margin lever.
- Acquisition cost above ASP (non-GPO purchasing): Medicare and MA infusions turn loss-making.
- the owned specialty pharmacy inside the big payers' specialty networks, or white bagging below the assumed tiers: the 2028
  exposure shrinks.
- Referral data showing Northeast Ohio demand already served. Weight-stability of the ranking is moderate
  (mean top-10 overlap 50%), so referral data should outweigh it.

**The three internal numbers that would sharpen this most:** commercial drug terms by payer, invoice
acquisition cost vs ASP for the top 10 drugs, and the active patient panel by drug and payer.

*Every figure above is filled from `outputs/*.json` by `make memo`; `tests/test_memo.py` fails if a number
in the memo cannot be traced to the model.*

---

## Architecture

```mermaid
flowchart LR
  subgraph Public sources
    A[CMS ASP files 2017Q1-2026Q4]:::src
    B[CMS PFS RVU26D + GPCI]:::src
    C[CMS Physician & Other Practitioners<br/>provider / service / geography 2013-2024]:::src
    D[CMS Part B spending, enrollment, hospitals]:::src
    E[CDC PLACES, Census PEP, ZCTA, Gazetteer, OMB CBSA]:::src
  end
  A & B & C & D & E -->|make ingest: filtered pulls + manifest| R[(data/raw 44.3 MB)]
  R -->|dbt build: 26 models, 36 tests| W[(DuckDB star schema)]
  W --> F[price path<br/>validation/test backtests] --> M[plan engine<br/>lag, net revenue, demand volume, fixed/variable]
  M --> S[2027 scenarios + 2028 bridge] --> X[Excel<br/>live formulas]
  M --> V[budget by site/month] --> VA[variance bridge<br/>vs SYNTHETIC actuals]
  W --> BM[benchmark] & MK[white space]
  S & V & VA & BM & MK --> EX[exports/*.csv] --> P[PBIP / TMDL<br/>25 sliceable DAX measures] & Q[SQL twins -> kpis.json]
  EX --> H[HTML scorecard] & G[Power BI build guide]
  S & BM & MK --> MEMO[decision memo]
  classDef src fill:#eef3fb,stroke:#2a78d6
```

## Data sources (all public; filtered pulls; see `data_manifest.json` and ADR 0002)

| Source | Used for | Link | License / terms |
|---|---|---|---|
| CMS ASP payment-limit files (40 quarters) | price path, lag, IRA flags, "lesser of" | [cms.gov ASP files](https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files) | US Government work. Only HCPCS Level II kept (pre-2021 files sit behind the CMS/AMA CPT page) |
| CMS PFS RVU26D, GPCI | admin fees (CY2026 RVUs, CY2027 proposed CF) | [PFS files](https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files) | Public; no CPT descriptors stored |
| Medicare Physician & Other Practitioners | dose, admins/patient, drug mix by specialty, benchmarks, supply | [data.cms.gov](https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners) | Public; rows < 11 beneficiaries suppressed |
| Medicare Part B Spending by Drug | 2025 out-of-sample check; realization reconciliation | [data.cms.gov](https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug/medicare-part-b-spending-by-drug) | Public |
| Medicare Monthly Enrollment; Hospital General Information | Ohio FFS vs MA split; hospital-heavy market flag | [enrollment](https://data.cms.gov/summary-statistics-on-beneficiary-enrollment/medicare-and-medicaid-reports/medicare-monthly-enrollment), [hospitals](https://data.cms.gov/provider-data/dataset/xubh-q36u) | Public |
| CMS IPAY 2028 list; IRA s.11403 biosimilar FAQ | MFP exposure; +8% window | [fact sheet](https://www.cms.gov/files/document/factsheet-medicare-negotiation-selected-drug-list-ipay-2028.pdf), [FAQ](https://www.cms.gov/files/document/biosimilar-faqs.pdf) | Public |
| CDC PLACES; Census PEP, ZCTA, Gazetteer; OMB CBSA | demand, population, geography, metros | [PLACES](https://data.cdc.gov/resource/i46a-9kgh.json), [census.gov](https://www.census.gov/programs-surveys/popest.html) | Public domain (ACS API needs a key, so PEP is used) |
| A regional operator's public website | footprint, published drug list (the plan formulary) | not linked in the public version | Public pages only (ADR 0001) |

## How to run

```bash
make init          # uv env with pinned deps + Chromium for screenshots
make check         # lint + dbt on fixtures + pytest (88 test functions, incl. regeneration on fixtures)
make reproduce     # full rebuild from public pulls
make monthly-pack  # month-end pack: refresh, DQ, budget vs actual bridge, memo, scorecard (OFFLINE=1 skips the pull)
```
data.cms.gov rate-limits repeated full pulls (HTTP 429); `make ingest` backs off, writes the manifest after each
source and caches the ~360 provider-service calls, so a throttled run resumes. A fresh `make reproduce`
re-pulled all 15 sources byte-identical (sha256) to the first pull. Open `excel/infusion_plan_2027_scenarios.xlsx` (blue cells are inputs), `docs/scorecard.html`,
and follow `docs/powerbi_build_guide.md` to build the report pages in Power BI Desktop.

## Results (every value is produced by the command / file shown)

| Area | Metric | Value | Source |
|---|---|---|---|
| Data | raw sources / size | 15 / 44.3 MB | `data_manifest.json` |
| Data model | dbt models / tests / business-rule tests (all pass) | 26 / 36 / 10 | `outputs/dbt_summary.json` |
| Mechanics | ASP+6% after sequestration (full coinsurance collection); Ohio 96413 at CY2027 proposed CF | ASP + 4.3%; $120.65 | `outputs/margin.json` |
| Pricing | Medicare paid below current price: raw / after sequestration / after sequestration + coinsurance (drug-quarters; $-weighted) | 6.2% / 12.0% / 30% (36%) | `outputs/margin.json` |
| Plan 2027 | contribution / operating margin / infusions / utilization | $3,767,531 / $2,734,116 / 7,413 / 67% | `outputs/scenarios.json` |
| Plan 2027 | contribution per infusion: Medicare FFS / MA / commercial | $172 / $68 / $946 | `outputs/scenarios.json` |
| Growth | added chair at current demand / 100 more patients / added-chair break-even utilization | -$57K / $222K / 12% | `outputs/scenarios.json` |
| Forecast | quarterly ASP, untouched test window, same 978 forecasts: naive / selected (33 modelled, 32 held flat) | 4.8% / 5.2%; per-series DM at h=1: 1 better / 1 worse of 16 | `outputs/forecast.json` |
| Forecast | annual volume MAPE naive / selected; spend MAPE naive / selected | 16.4% / 20.0%; 20.2% / 27.9% | `outputs/forecast.json` |
| Forecast | 80% interval coverage on the test window: ASP / volume / spend | 77% / 77% / 71% | `outputs/forecast.json` |
| Excel | live formulas / max rel. diff vs Python (default + stressed inputs, LibreOffice recalc) | 1,757 / 5.2e-06 | `outputs/excel_recalc_check.json` |
| Benchmark | clinicians scored / provider-molecule pairs fully observed / above vs below state | 7,649 / 0% of 284 / 2 vs 0 | `outputs/benchmark.json` |
| Market | eligible markets / Canton-Massillon, OH rank, share of weightings in top 10 / mean top-10 overlap | 74 / 2, 76% / 50% | `outputs/market.json` |
| Power BI | TMDL tables / DAX measures (each mapped to a SQL twin; several checked independently in pandas) | 23 / 25 | `tests/test_tmdl.py` |
| Variance (**SYNTHETIC** actuals) | Site A Jan-Mar: total = volume + mix + rate | $-68,232 = $-47,020 + $-20,296 + $-916 | `outputs/variance_pack_SYNTHETIC.json` |
| RCM (**SYNTHETIC**) | clean-claim / denial / days in AR / net collection | 81.9% / 11.2% / 57.0 / 91.0% | `outputs/rcm_kpis_SYNTHETIC.json` |
| Automation | DQ pass / flag / fail; manual steps replaced (est. hours) / measured run | 7 / 3 / 0; 19 (12.2 h est.) / 0.6 min | `outputs/monthly_pack_last.json` |

## How this maps to the job

| FP&A work in the JD | Where it lives here |
|---|---|
| Power BI dashboards and scorecards | `powerbi/`: star schema, date table, site / payer / drug / month slicing, budget vs actual measures; `docs/powerbi_build_guide.md` |
| Clean, join, validate multi-source data | `dbt/`: one star schema from the public sources; HCPCS continuity, biosimilar qualification, exact reconciliation to CMS's published averages, suppression-aware sums |
| Financial / payer analysis | per-infusion economics by drug x payer with net collection; product x payer biosimilar decisions; tornado |
| Forecasting, budgeting, variance | backtested price/volume forecasts; 2027 plan by site and month; volume/mix/rate bridge; Excel model |
| Benchmarking, market analysis, growth | state-level biosimilar adoption, suppression-aware provider intervals; metro white-space ranking; chair vs patient growth economics |
| Revenue cycle | KPI logic on **SYNTHETIC** 837/835 data, and net-collection factors per payer as plan drivers |
| Automate recurring workflows | `make monthly-pack`: refresh, DQ, variance bridge, memo, scorecard (19 manual steps) |
| Executive communication | `docs/MEMO.md`: recommendation, risks, what would change it |

## Known limitations / what differs from production
- **Practice inputs are assumptions** (`config/assumptions.yaml`): patient panel, payer mix, service-line
  split, contract terms, collection rates and costs. Absolute dollars are illustrative; the tornado shows
  each one's weight.
- **Drug mix**: national in-office Medicare billing by neurologists and rheumatologists, restricted to
  the operator's published drugs, with Ohio biosimilar shares on the listed products. Hospital-administered
  MS infusion is not in physician data.
- **2027 prices** follow the models chosen on a decision window. The untouched test window shows no
  systematic edge over naive (naive slightly better on matched forecasts), and both under-forecast rising
  prices. The lag-drift scenario (historical lag spreads persist) is the price-risk sensitivity. Acquisition
  is proxied by ASP; for WAC-priced ("lesser of") codes the base buys at WAC. The 70% stress bound is not a
  credible purchase price and is shown only as a bound.
- **ZIP to county**: Census ZCTAs first; unique and campus ZIPs (e.g. 44195, Cleveland Clinic) fall back to
  the county most providers in the same USPS city and state map to. `make dq` fails if more than 0.5% of
  region specialists stay unmapped.
- **Allowed vs payment limit**: physician-PUF allowed per unit is 96.4% of the payment limit, and Part B
  Spending per unit is 97.8%, including for flat-price codes. That makes it a systematic or
  definitional effect, not a practice risk, so it is excluded from the plan (`make dq` keeps it under watch).
- **2027 PFS** uses CY2026 RVUs with the proposed CY2027 CF. **2028** applies 2028 rules to 2027 prices.
  **MFPs** (due 2026-11-30) are an assumed discount.
- **Benchmarking**: CMS suppression leaves no provider-molecule pair fully observed, so provider labels are
  interval-based and mostly "insufficient data". State-level adoption is the reliable comparison.
- **Market**: arthritis prevalence is all-type. Hospital outpatient infusion volume is not public at market
  level, so hospital-heavy markets are flagged by hospital density instead of being scored.
- **Power BI: the PBIP has not been opened in Power BI Desktop** (built on macOS). Each measure is mapped to
  a SQL twin in a stated filter context; the budget, variance and adoption twins are re-derived
  independently in pandas. The DAX itself has never been executed. Report pages are built by hand from the
  guide.
- **SYNTHETIC data** (RCM, monthly actuals) supports no conclusion.

ADRs for the decisions an interviewer will probe are in `docs/decisions/`. Acceptance evidence is in
`docs/ACCEPTANCE.md`.
