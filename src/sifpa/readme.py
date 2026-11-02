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
    m, fc, bm, mk, sc, kp, dbt, xl, rcm, dq, var = (J(x) for x in (
        "margin.json", "forecast.json", "benchmark.json", "market.json", "scenarios.json", "kpis.json",
        "dbt_summary.json", "excel_recalc_check.json", "rcm_kpis_SYNTHETIC.json", "dq_report.json",
        "variance_pack_SYNTHETIC.json"))
    man = json.loads((ROOT / "data_manifest.json").read_text())
    pack = J("monthly_pack_last.json") if (OUTPUTS / "monthly_pack_last.json").exists() else {}
    qa, av, asp_ = fc["quarterly_asp"], fc["annual"]["administrations"], fc["annual"]["allowed"]
    dm = qa["dm_selected_vs_naive_by_h"]
    s1 = next(r for r in var["by_site_ytd"] if r["site_id"] == "S1")
    tables = len(list((ROOT / "powerbi/SpecialtyInfusionFPA.SemanticModel/definition/tables").glob("*.tmdl")))
    real = next(c for c in dq["checks"] if c["check"] == "allowed_vs_payment_limit_explained")["detail"]
    f = lambda x: f"${x:,.0f}"  # noqa: E731
    n.update({
        "raw_sources": str(len([k for k in man if not k.startswith("_")])), "raw_mb": f"{man['_total_raw_mb']:.1f}",
        "dbt_models": str(dbt["models"]), "dbt_tests": str(dbt["tests"]), "dbt_rules": str(dbt["business_rule_tests"]),
        "fee_96413": f"${m['ohio_admin_fee_96413_cf2027']:.2f}",
        "lag_median": f"{m['median_lag_spread_pct_last8_reference_single_source'] * 100:.1f}%",
        "uw_raw": f"{m['underwater']['raw']['share_drug_quarters'] * 100:.1f}%",
        "uw_seq": f"{m['underwater']['after_sequestration']['share_drug_quarters'] * 100:.1f}%",
        "n_drugs_priced": str(m["n_drugs_priced"]),
        "asp_series": str(qa["n_series_modelled"]), "asp_held": str(qa["n_held"]),
        "dm_p_min": f"{min(d['p_value'] for d in dm.values() if d['p_value'] is not None):.3f}",
        "dm_p_max": f"{max(d['p_value'] for d in dm.values() if d['p_value'] is not None):.3f}",
        "vol_naive": f"{av['test_mape_naive'] * 100:.1f}%", "vol_sel": f"{av['test_mape_selected'] * 100:.1f}%",
        "spend_naive": f"{asp_['test_mape_naive'] * 100:.1f}%", "spend_sel": f"{asp_['test_mape_selected'] * 100:.1f}%",
        "vol_cov": f"{av['pi80_test_coverage_overall'] * 100:.0f}%", "spend_cov": f"{asp_['pi80_test_coverage_overall'] * 100:.0f}%",
        "xl_formulas": f"{xl['n_formulas']:,}", "xl_diff": f"{xl['max_rel_diff']:.1e}",
        "providers": f"{bm['n_providers_scored']:,}", "pairs": str(bm["n_provider_molecule_pairs"]),
        "pairs_full": f"{bm['share_pairs_fully_observed'] * 100:.0f}%",
        "above_state": str(bm["provider_level_flags"].get("above_state", 0)),
        "below_state": str(bm["provider_level_flags"].get("below_state", 0)),
        "pbi_tables": str(tables), "pbi_measures": str(len(kp)),
        "var_s1": f(s1["variance"]), "var_vol": f(s1["volume"]), "var_mix": f(s1["mix"]), "var_rate": f(s1["rate"]),
        "rcm_ccr": f"{rcm['clean_claim_rate'] * 100:.1f}%", "rcm_denial": f"{rcm['denial_rate'] * 100:.1f}%",
        "rcm_ar": f"{rcm['days_in_ar']:.1f}", "rcm_ncr": f"{rcm['net_collection_rate'] * 100:.1f}%",
        "dq_pass": str(dq["n_pass"]), "dq_flag": str(dq["n_flag"]), "dq_fail": str(dq["n_fail"]),
        "real_puf": f"{real['median_puf_allowed_ratio'] * 100:.1f}%", "real_spend": f"{real['median_partb_spend_ratio'] * 100:.1f}%",
        "pack_steps": str(pack.get("manual_steps_replaced", "n/a")), "pack_hours": str(pack.get("manual_hours_estimate", "n/a")),
        "pack_minutes": str(pack.get("automated_minutes_measured", "n/a")),
        "nat_chair": f"{fc['national_inoffice_admins_2024']['chair']:,}",
        "nat_chair_cagr": f"{fc['national_inoffice_admin_cagr_2019_2024']['chair'] * 100:.1f}%",
        "base_contrib_exact": f(sc["scenarios"]["base"]["contribution"]),
        "base_op_exact": f(sc["scenarios"]["base"]["operating_margin"]),
    })
    return n


TEMPLATE = """# specialty-infusion-fpa

**In-office infusion FP&A for a multi-site inflammatory-disease practice, built on public CMS data:** what
infusion really earns, how exposed it is to biosimilar, ASP and policy shifts, where growth should come from,
and how the plan becomes a monthly budget-vs-actual pack. It is written for the EVP of FP&A at a
regional inflammatory-disease practice. It uses public data only, and I have no affiliation with the operator it is modelled on.

> **Headline (2027 basis):** an illustrative {chairs}-chair suite on a regional operator's published drug list makes
> **{op_margin}** operating margin on {admins} infusions. Medicare FFS contributes **{med}** per infusion,
> because its drug margin is **{med_margin_pct}** after sequestration, coinsurance bad debt and denials. The
> assumed commercial contract contributes **{com}**, so commercial is {com_contrib} of contribution. The 2028
> risk is white bagging ({wb}), not Medicare negotiation ({mfp} on the listed drugs). Grow by patients
> (100 more add {plus100}), not chairs (one more costs {chair_fixed}/yr at {util} utilization). Next site:
> **Northeast Ohio**: {oh1} (gap leader, needs recruited rheumatologists) or Cleveland (larger base).

| Problem | What I built | Key results (real numbers, reproducible) |
|---|---|---|
| Next year's plan needs to know what infusion earns and how fragile it is | Buy-and-bill engine on the real 2-quarter lag (pay on ASP t-2, buy at ASP t), biosimilar add-on on *reference* ASP, net collection for every payer, demand-driven volume, fixed vs variable cost | Medicare FFS {med}, MA {ma}, commercial {com} per infusion. Commercial markup range moves operating margin {cm_lo} to {cm_hi} |
| Policy and product shifts hit at different times | Product x payer biosimilar decision table; cost-tiered white bagging with owned-pharmacy recapture; 2028 run-rate bridge; Excel with {xl_formulas} live formulas | Listed biosimilars {listed_delta}; best product per payer up to {best_delta} (only {n_robust}/{n_best} picks robust); 2028 {p28_delta} |
| Growth and the monthly pack | Market-grain white-space ranking (cross-state metros whole, prescriber floor); budget by site/month + SYNTHETIC actuals with a volume/mix/rate bridge; sliceable Power BI model | {oh1}: rank {oh1_rank} of {n_markets}. Site A Q1 variance (SYNTHETIC) {var_s1} = volume {var_vol} + mix {var_mix} + rate {var_rate} |

![Executive page of the scorecard](docs/img/scorecard_exec.png)

---

{memo_body}

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
  A & B & C & D & E -->|make ingest: filtered pulls + manifest| R[(data/raw {raw_mb} MB)]
  R -->|dbt build: {dbt_models} models, {dbt_tests} tests| W[(DuckDB star schema)]
  W --> F[price path<br/>validation/test backtests] --> M[plan engine<br/>lag, net revenue, demand volume, fixed/variable]
  M --> S[2027 scenarios + 2028 bridge] --> X[Excel<br/>live formulas]
  M --> V[budget by site/month] --> VA[variance bridge<br/>vs SYNTHETIC actuals]
  W --> BM[benchmark] & MK[white space]
  S & V & VA & BM & MK --> EX[exports/*.csv] --> P[PBIP / TMDL<br/>{pbi_measures} sliceable DAX measures] & Q[SQL twins -> kpis.json]
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
make check         # lint + dbt on fixtures + pytest ({n_tests} test functions, incl. regeneration on fixtures) + strict feature gate
make reproduce     # full rebuild from public pulls
make monthly-pack  # month-end pack: refresh, DQ, budget vs actual bridge, memo, scorecard (OFFLINE=1 skips the pull)
```
data.cms.gov rate-limits repeated full pulls (HTTP 429); `make ingest` backs off and writes the manifest after
each source. Open `excel/infusion_plan_2027_scenarios.xlsx` (blue cells are inputs), `docs/scorecard.html`,
and follow `docs/powerbi_build_guide.md` to build the report pages in Power BI Desktop.

## Results (every value is produced by the command / file shown)

| Area | Metric | Value | Source |
|---|---|---|---|
| Data | raw sources / size | {raw_sources} / {raw_mb} MB | `data_manifest.json` |
| Data model | dbt models / tests / business-rule tests (all pass) | {dbt_models} / {dbt_tests} / {dbt_rules} | `outputs/dbt_summary.json` |
| Mechanics | ASP+6% after sequestration (full coinsurance collection); Ohio 96413 at CY2027 proposed CF | ASP + {net_addon}; {fee_96413} | `outputs/margin.json` |
| Pricing | Medicare paid below current price: raw / after sequestration / after sequestration + coinsurance (drug-quarters; $-weighted) | {uw_raw} / {uw_seq} / {uw} ({uw_d}) | `outputs/margin.json` |
| Plan 2027 | contribution / operating margin / infusions / utilization | {base_contrib_exact} / {base_op_exact} / {admins} / {util} | `outputs/scenarios.json` |
| Plan 2027 | contribution per infusion: Medicare FFS / MA / commercial | {med} / {ma} / {com} | `outputs/scenarios.json` |
| Growth | added chair at current demand / 100 more patients / added-chair break-even utilization | {chair_value} / {plus100} / {chair_be} | `outputs/scenarios.json` |
| Forecast | quarterly ASP, test window MAPE: naive / validation-selected ({asp_series} modelled, {asp_held} held flat) | {asp_naive} / {asp_sel}; DM p {dm_p_min}-{dm_p_max} (selected worse) | `outputs/forecast.json` |
| Forecast | annual volume MAPE naive / selected; spend MAPE naive / selected | {vol_naive} / {vol_sel}; {spend_naive} / {spend_sel} | `outputs/forecast.json` |
| Forecast | 80% interval coverage on the test window: ASP / volume / spend | {asp_cov} / {vol_cov} / {spend_cov} | `outputs/forecast.json` |
| Excel | live formulas / max rel. diff vs Python (default + stressed inputs, LibreOffice recalc) | {xl_formulas} / {xl_diff} | `outputs/excel_recalc_check.json` |
| Benchmark | clinicians scored / provider-molecule pairs fully observed / above vs below state | {providers} / {pairs_full} of {pairs} / {above_state} vs {below_state} | `outputs/benchmark.json` |
| Market | eligible markets / {oh1} rank, share of weightings in top 10 / mean top-10 overlap | {n_markets} / {oh1_rank}, {oh1_s} / {overlap} | `outputs/market.json` |
| Power BI | TMDL tables / DAX measures (each mapped to a SQL twin; several checked independently in pandas) | {pbi_tables} / {pbi_measures} | `tests/test_tmdl.py` |
| Variance (**SYNTHETIC** actuals) | Site A Jan-Mar: total = volume + mix + rate | {var_s1} = {var_vol} + {var_mix} + {var_rate} | `outputs/variance_pack_SYNTHETIC.json` |
| RCM (**SYNTHETIC**) | clean-claim / denial / days in AR / net collection | {rcm_ccr} / {rcm_denial} / {rcm_ar} / {rcm_ncr} | `outputs/rcm_kpis_SYNTHETIC.json` |
| Automation | DQ pass / flag / fail; manual steps replaced (est. hours) / measured run | {dq_pass} / {dq_flag} / {dq_fail}; {pack_steps} ({pack_hours} h est.) / {pack_minutes} min | `outputs/monthly_pack_last.json` |

## How this maps to the job

| FP&A work in the JD | Where it lives here |
|---|---|
| Power BI dashboards and scorecards | `powerbi/`: star schema, date table, site / payer / drug / month slicing, budget vs actual measures; `docs/powerbi_build_guide.md` |
| Clean, join, validate multi-source data | `dbt/`: one star schema from the public sources; HCPCS continuity, biosimilar qualification, exact reconciliation to CMS's published averages, suppression-aware sums |
| Financial / payer analysis | per-infusion economics by drug x payer with net collection; product x payer biosimilar decisions; tornado |
| Forecasting, budgeting, variance | backtested price/volume forecasts; 2027 plan by site and month; volume/mix/rate bridge; Excel model |
| Benchmarking, market analysis, growth | state-level biosimilar adoption, suppression-aware provider intervals; metro white-space ranking; chair vs patient growth economics |
| Revenue cycle | KPI logic on **SYNTHETIC** 837/835 data, and net-collection factors per payer as plan drivers |
| Automate recurring workflows | `make monthly-pack`: refresh, DQ, variance bridge, memo, scorecard ({pack_steps} manual steps) |
| Executive communication | `docs/MEMO.md`: recommendation, risks, what would change it |

## Known limitations / what differs from production
- **Practice inputs are assumptions** (`config/assumptions.yaml`): patient panel, payer mix, service-line
  split, contract terms, collection rates and costs. Absolute dollars are illustrative; the tornado shows
  each one's weight.
- **Drug mix**: national in-office Medicare billing by neurologists and rheumatologists, restricted to
  the operator's published drugs, with Ohio biosimilar shares on the listed products. Hospital-administered
  MS infusion is not in physician data.
- **Prices are held flat for 2027** because no model beat naive on the test window. The lag mechanics are
  built in, but they produce no spread on a flat path. Acquisition is proxied by ASP; for WAC-priced
  ("lesser of") codes the proxy is a lower bound, and a range is shown.
- **Allowed vs payment limit**: physician-PUF allowed per unit is {real_puf} of the payment limit, and Part B
  Spending per unit is {real_spend}, including for flat-price codes. That makes it a systematic or
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
