"""`make readme`: render README.md from outputs/*.json + docs/MEMO.md so README numbers cannot drift.

tests/test_readme_numbers.py re-renders and diffs, and spot-checks headline numbers against the JSON.
"""

from __future__ import annotations

import json

from sifpa import memo
from sifpa.paths import DOCS, OUTPUTS, ROOT


def J(name: str) -> dict:
    return json.loads((OUTPUTS / name).read_text())


def facts() -> dict[str, str]:
    n = memo.numbers()
    m, fc, bm, mk, sc, kp, dbt, xl, rcm, dq = (J(x) for x in (
        "margin.json", "forecast.json", "benchmark.json", "market.json", "scenarios.json", "kpis.json",
        "dbt_summary.json", "excel_recalc_check.json", "rcm_kpis_SYNTHETIC.json", "dq_report.json"))
    man = json.loads((ROOT / "data_manifest.json").read_text())
    pack = J("monthly_pack_last.json") if (OUTPUTS / "monthly_pack_last.json").exists() else {}
    qa, an = fc["quarterly_asp"], fc["annual"]
    cov = [r["coverage_80"] for r in qa["pi80_coverage_eval"] + an["pi80_coverage_eval"]]
    tables = len(list((ROOT / "powerbi/SpecialtyInfusionFPA.SemanticModel/definition/tables").glob("*.tmdl")))
    n.update({
        "raw_sources": str(len([k for k in man if not k.startswith("_")])),
        "raw_mb": f"{man['_total_raw_mb']:.1f}",
        "dbt_models": str(dbt["models"]), "dbt_tests": str(dbt["tests"]), "dbt_rules": str(dbt["business_rule_tests"]),
        "fee_96413": f"${m['ohio_admin_fee_96413']:.2f}",
        "chair_cost": f"${m['chair_cost_per_hour']:.2f}",
        "lag_median": f"{m['median_lag_spread_pct_last8_reference_single_source'] * 100:.1f}%",
        "underwater": f"{m['share_quarters_underwater_all_drugs'] * 100:.1f}%",
        "n_drugs_priced": str(m["n_drugs_priced"]),
        "asp_series": str(qa["n_series"]), "vol_series": str(an["n_series"]),
        "asp_beats_naive": f"{qa['share_series_best_beats_naive'] * 100:.0f}%",
        "cov_min": f"{min(cov) * 100:.0f}%", "cov_max": f"{max(cov) * 100:.0f}%",
        "ext_n": str(fc["external_2025"]["n_molecules"]),
        "xl_formulas": f"{xl['n_formulas']:,}", "xl_diff": f"{xl['max_rel_diff']:.1e}",
        "providers": f"{bm['n_providers_scored']:,}",
        "above_peer": str(bm["biosimilar_vs_peer_counts"].get("above_peer", 0)),
        "below_peer": str(bm["biosimilar_vs_peer_counts"].get("below_peer", 0)),
        "pbi_tables": str(tables), "pbi_measures": str(len(kp)),
        "rcm_ccr": f"{rcm['clean_claim_rate'] * 100:.1f}%", "rcm_denial": f"{rcm['denial_rate'] * 100:.1f}%",
        "rcm_ar": f"{rcm['days_in_ar']:.1f}", "rcm_ncr": f"{rcm['net_collection_rate'] * 100:.1f}%",
        "dq_pass": str(dq["n_pass"]), "dq_flag": str(dq["n_flag"]), "dq_fail": str(dq["n_fail"]),
        "pack_steps": str(pack.get("manual_steps_replaced", "n/a")),
        "pack_hours": str(pack.get("manual_hours_estimate", "n/a")),
        "pack_minutes": str(pack.get("automated_minutes_measured", "n/a")),
        "push_contrib": f"${sc['scenarios']['biosimilar_push']['annual']['contribution'] / 1e6:.2f}M",
        "shock_contrib": f"${sc['scenarios']['policy_shock']['annual']['contribution'] / 1e6:.2f}M",
        "base_contrib_exact": f"${sc['scenarios']['base']['annual']['contribution']:,}",
    })
    return n


TEMPLATE = """# specialty-infusion-fpa

**In-office infusion FP&A for a multi-site inflammatory-disease practice, built on public CMS data:** how much
margin infusion really makes, how exposed it is to biosimilar, ASP and Medicare-negotiation shifts, and where
the next site should go. It is written for the EVP of FP&A at a regional inflammatory-disease practice. It uses public data
only, and I have no affiliation with the operator it is modelled on.

> **Headline:** a chair infusion earns about **{per_admin_2027}** in 2027 (base case). Medicare FFS contributes
> **{med_per_admin}** per infusion. Its drug margin is **{med_drug_margin_pct}** after sequestration and
> coinsurance bad debt. The assumed commercial contract contributes **{com_per_admin}**, so commercial is
> {com_share_contrib} of infusion contribution. A blanket biosimilar push *lowers* contribution
> ({push_delta}). The 2028 policy stack (MFP + white bagging) changes contribution by **{shock_delta}** a year. The next site:
> **{oh_market}** (strongest Ohio market outside Columbus, P(top 10) = {oh_p}).

| Problem | What I built | Key results (real numbers, reproducible) |
|---|---|---|
| Next year's plan needs to know how much margin infusion makes and how fragile it is | Buy-and-bill engine: ASP+6% with the 2-quarter lag, biosimilar add-on on *reference* ASP, sequestration, Ohio PFS admin fees, observed dose per infusion. Tornado over every assumption | Medicare drug margin {med_drug_margin_pct} of drug revenue. Break-even acquisition price ASP+{breakeven_spread}. Measured 2024 allowed/PL realization {realization} |
| Policy shifts (biosimilars, IRA +8% expiry, MFP 2028, PFS cut) hit at different times | Backtested forecasts (ASP MAPE {asp_mape_ets} vs naive {asp_mape_naive}). 3 scenarios in Python **and** an Excel workbook with {xl_formulas} live formulas | Base {contrib_2027}, biosimilar push {push_delta}, policy shock {shock_delta} (illustrative {chairs}-chair suite) |
| Growth: where to add sites, chairs or providers | Market-grain white-space ranking (7 states, {n_markets} eligible markets) with a 2,000-draw weight-stability test; provider benchmarks with EB shrinkage | {oh_market}: rank {oh_rank}, P(top 10) {oh_p}. One chair = {per_chair}/yr. Each 5 pts of utilization = {per_util_pt} |

![Executive page of the scorecard](docs/img/scorecard_exec.png)

---

{memo_body}

*Every figure above is filled from `outputs/*.json` by `make memo` (`src/sifpa/memo.py`); `tests/test_memo.py`
fails if a number in the memo cannot be traced to the model.*

---

## Architecture

```mermaid
flowchart LR
  subgraph Public sources
    A[CMS ASP files 2017Q1-2026Q4]:::src
    B[CMS PFS RVU26D + GPCI]:::src
    C[CMS Physician & Other Practitioners<br/>provider / service / geography 2013-2024]:::src
    D[CMS Part B spending + enrollment]:::src
    E[CDC PLACES, Census PEP, ZCTA, Gazetteer, OMB CBSA]:::src
  end
  A & B & C & D & E -->|make ingest: filtered API pulls + manifest| R[(data/raw Parquet {raw_mb} MB)]
  R -->|dbt build: {dbt_models} models, {dbt_tests} tests| W[(DuckDB star schema)]
  W --> M[margin engine] --> S[2027 scenarios] --> X[Excel workbook<br/>live formulas]
  W --> F[backtested forecasts] --> S
  W --> BM[benchmark] & MK[white space]
  W & M & S & BM & MK --> EX[exports/*.csv] --> P[PBIP / TMDL<br/>{pbi_measures} DAX measures] & Q[SQL twins -> kpis.json]
  EX --> H[HTML scorecard + screenshots]
  M & S & F & BM & MK --> MEMO[decision memo]
  SYN[SYNTHETIC 837/835] --> RCM[RCM KPI layer] --> EX
  classDef src fill:#eef3fb,stroke:#2a78d6
```

## Data sources (all public; filtered pulls; see `data_manifest.json` and ADR 0002)

| Source | Used for | Link | License / terms |
|---|---|---|---|
| CMS ASP payment-limit files (40 quarters) + NDC-HCPCS crosswalk | prices, implied ASP, lag spread, IRA flags | [cms.gov ASP pricing files](https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files) | US Government work. Pre-2021 files sit behind the CMS/AMA CPT license page; only HCPCS Level II codes are kept |
| CMS PFS RVU26D, GPCI, localities | admin fees (96413/96415/96365/96366/96372) | [PFS relative value files](https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files) | Public. CPT codes are AMA copyright: no descriptors stored |
| Medicare Physician & Other Practitioners (by provider and service / provider / geography and service) | dose, volume, mix, benchmarks, supply | [data.cms.gov](https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners) | Public. Rows < 11 beneficiaries suppressed by CMS |
| Medicare Part B Spending by Drug (annual + quarterly) | 2025 out-of-sample check | [data.cms.gov Part B spending](https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug/medicare-part-b-spending-by-drug) | Public |
| Medicare Monthly Enrollment (county) | Original Medicare vs MA share | [data.cms.gov enrollment](https://data.cms.gov/summary-statistics-on-beneficiary-enrollment/medicare-and-medicaid-reports/medicare-monthly-enrollment) | Public |
| CMS IPAY 2028 selected drugs; CMS biosimilar (IRA s.11403) FAQ | MFP exposure, +8% window | [fact sheet](https://www.cms.gov/files/document/factsheet-medicare-negotiation-selected-drug-list-ipay-2028.pdf), [FAQ](https://www.cms.gov/files/document/biosimilar-faqs.pdf) | Public |
| CDC PLACES county 2025 (2024 for KY/PA) | arthritis prevalence | [data.cdc.gov](https://data.cdc.gov/resource/i46a-9kgh.json) | Public domain |
| Census PEP vintage 2025, ZCTA-county 2020, Gazetteer 2025, OMB CBSA 2023 | population, 65+, geography | [census.gov](https://www.census.gov/programs-surveys/popest.html) | Public domain. The ACS API now needs a key, so PEP is used instead |
| operator website (public pages) | footprint, drug list, geography choice | not linked in the public version | Public information only (ADR 0001) |

## How to run

```bash
make init          # uv env with pinned deps + Chromium for screenshots
make check         # offline gate: ruff + pytest ({n_tests} test functions) + dbt on fixtures + feature regression
make reproduce     # full rebuild from public pulls (~5 min, ~{raw_mb} MB raw)
make monthly-pack  # the recurring refresh, timed step by step
```
Open `excel/infusion_plan_2027_scenarios.xlsx` (change any blue input) and `docs/scorecard.html`. On Windows,
open `powerbi/SpecialtyInfusionFPA.pbip` after setting the `RepoPath` parameter.

## Results (every value is produced by the command / file shown)

| Area | Metric | Value | Source |
|---|---|---|---|
| Data | raw sources / size / ASP quarters | {raw_sources} / {raw_mb} MB / 40 | `data_manifest.json` |
| Data model | dbt models / tests / business-rule tests (all pass) | {dbt_models} / {dbt_tests} / {dbt_rules} | `outputs/dbt_summary.json` |
| Mechanics | ASP+6% after sequestration (full coinsurance collection) | ASP + {net_addon} | `outputs/margin.json` |
| Mechanics | Ohio CY2026 non-facility 96413 / chair cost per hour | {fee_96413} / {chair_cost} | `outputs/margin.json` |
| Pricing | median lag spread (ref/single-source, last 8 qtrs) / underwater drug-quarters | {lag_median} / {underwater} | `outputs/lag_spread_by_drug.csv` |
| Margin | contribution per infusion: Medicare FFS / commercial (2027 base) | {med_per_admin} / {com_per_admin} | `outputs/scenarios.json` |
| Margin | allowed / payment limit, 2024 in-office (measured) | {realization} | `outputs/margin.json` |
| Forecast | quarterly ASP MAPE: damped ETS / naive / seasonal naive ({asp_series} drugs, h=1-4) | {asp_mape_ets} / {asp_mape_naive} / {asp_mape_snaive} | `outputs/forecast.json` |
| Forecast | annual volume+spend MAPE: damped ETS / naive ({vol_series} series, h=1-2) | {vol_mape_ets} / {vol_mape_naive} | `outputs/forecast.json` |
| Forecast | 80% PI coverage on held-out origins (all models) | {cov_min} to {cov_max} | `outputs/forecast.json` |
| Forecast | 2025 out-of-sample spend MAPE: damped ETS / naive ({ext_n} molecules) | {ext_mape_ets} / {ext_mape_naive} | `outputs/forecast_external_2025.csv` |
| Scenarios | 2027 contribution: base / biosimilar push / policy shock | {base_contrib_exact} / {push_contrib} / {shock_contrib} | `outputs/scenarios.json` |
| Excel | live formulas / max rel. diff vs Python after LibreOffice recalc | {xl_formulas} / {xl_diff} | `outputs/excel_recalc_check.json` |
| Benchmark | clinicians scored / biosimilar rates censored / above vs below peer | {providers} / {censored} / {above_peer} vs {below_peer} | `outputs/benchmark.json` |
| Benchmark | infliximab biosimilar share 2024: Ohio / US | {infl_bio_oh} / {infl_bio_us} | `outputs/benchmark.json` |
| Market | eligible markets / {oh_market} rank, P(top 10) / mean top-10 overlap | {n_markets} / {oh_rank}, {oh_p} / {overlap} | `outputs/market.json` |
| Power BI | TMDL tables / DAX measures, each with a SQL twin equal to `kpis.json` | {pbi_tables} / {pbi_measures} | `tests/test_tmdl.py` |
| RCM (**SYNTHETIC**) | clean-claim / denial / days in AR / net collection | {rcm_ccr} / {rcm_denial} / {rcm_ar} / {rcm_ncr} | `outputs/rcm_kpis_SYNTHETIC.json` |
| Automation | DQ checks pass / flag / fail; manual steps replaced (estimated hours) / measured run | {dq_pass} / {dq_flag} / {dq_fail}; {pack_steps} ({pack_hours} h est.) / {pack_minutes} min | `outputs/dq_report.json`, `outputs/monthly_pack_last.json` |

## How this maps to the job

| FP&A work in the JD | Where it lives here |
|---|---|
| Power BI dashboards and scorecards | `powerbi/` PBIP + TMDL (star schema, date table, {pbi_measures} documented DAX measures); `docs/scorecard.html` mirrors the pages |
| Clean, join, validate multi-source data | `dbt/`: 14 public sources into one star schema; tests for HCPCS continuity, biosimilar qualification, payment <= allowed, suppression-aware reconciliation, no fan-out |
| Financial / operational / payer analysis | per-infusion economics by drug and payer, lag spread, biosimilar conversion, tornado (`src/sifpa/margin.py`) |
| Forecasting, scenarios, plan support | backtested forecasts + 2027 scenarios; Excel workbook FP&A can edit (`excel/`) |
| Benchmarking, market analysis, growth | provider scorecards with EB shrinkage; white-space ranking at metro grain |
| Revenue cycle | KPI logic (clean-claim, CARC denials, days in AR, NCR) in SQL + DAX on **SYNTHETIC** 837/835 data, ready to point at real remits |
| Automate recurring workflows | `make monthly-pack` (timed, {pack_steps} manual steps replaced), DQ flags, CI |
| Executive communication | `docs/MEMO.md`: recommendation, risks, and what would change it |

## Known limitations / what differs from production
- **Medicare FFS only.** MA and commercial claims are not public. Commercial reimbursement, payer mix, chair
  count, utilization and costs are **labelled assumptions** (`config/assumptions.yaml`), so absolute dollars are
  illustrative. The tornado shows how much each one matters.
- **Acquisition cost is proxied by ASP.** GPO/contract prices, rebates, discarded-drug (JW/JZ) amounts and bad
  debt beyond coinsurance are not modelled. The measured **{realization} allowed/PL realization** is
  unexplained (unit-billing artifacts, MSP or deductible effects are candidates) and appears only as a downside.
- **2027 PFS** uses the July 2026 *proposed* conversion factor. **IPAY 2028 MFPs** were not published at build
  time, so the discount is an assumption.
- **CMS cell suppression (< 11)** censors provider-level biosimilar rates ({censored} of provider-molecule
  pairs). Adoption is therefore benchmarked at geography level, and provider ranks carry intervals.
- **Market analysis**: arthritis prevalence (all types) is a weak proxy for inflammatory disease. There is no
  public county MS prevalence. ZIP does not equal ZCTA. Supply counts are Medicare FFS billers only, and an infusion biller only
  counts where CMS shows a row (11 or more beneficiaries for a code), so supply is undercounted in small markets. Some CBSAs cross
  the region (flagged).
- **Forecasts**: the annual series are short (2013-2024), and per-series model choice is optimistic (ADR 0004).
- **Power BI: the PBIP has not been opened in Power BI Desktop** (built on macOS). The TMDL is validated
  structurally, and every measure's logic is mirrored by a SQL twin that reproduces the published value.
  Report pages are shells; the visual layout lives in the HTML scorecard.
- **RCM data is SYNTHETIC** and supports no conclusion.

Decisions an interviewer will probe are in `docs/decisions/` (8 ADRs). Acceptance evidence is in
`docs/ACCEPTANCE.md`.
"""


def build() -> str:
    f = facts()
    memo_text = (DOCS / "MEMO.md").read_text().replace("# Decision memo:", "## Executive decision memo:", 1)
    memo_text = memo_text.replace("\n## ", "\n### ").replace("### Executive decision memo:", "## Executive decision memo:", 1)
    n_tests = sum(p.read_text().count("\ndef test_") for p in (ROOT / "tests").glob("test_*.py"))
    return TEMPLATE.format(memo_body=memo_text.strip(), n_tests=n_tests, **f)


def main() -> None:
    (ROOT / "README.md").write_text(build())
    print("README.md written")


if __name__ == "__main__":
    main()
