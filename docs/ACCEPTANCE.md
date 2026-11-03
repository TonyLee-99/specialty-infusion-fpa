# Acceptance criteria

A1-A15 were written **before** building (commit `8553a3e`). A16-A24 were added in a second iteration,
before those changes were built. Each criterion ends PASS or FAIL with evidence: the command, plus an output
excerpt. A target that is missed is reported with its real number. Status as of 2026-11-02.

| # | Criterion (measurable) | Target | Status | Evidence (command -> excerpt) |
|---|---|---|---|---|
| A1 | Every source pulled via filtered API or small file, manifest with url/rows/sha256 | rows > 0; raw < 3 GB | **PASS** | `pytest tests/test_manifest.py` -> 4 passed. 15 sources, 44.3 MB. `make reproduce` from fresh network pulls passes end to end (log: `logs/reproduce.log`, 1m23s with the resumable provider_service cache); all 15 re-pulled files are byte-identical to the first pull (sha256) |
| A2 | dbt models + data tests pass on full warehouse and CI fixtures | >= 25 tests, >= 4 business rules, 0 failures | **PASS** | `outputs/dbt_summary.json`: 26 models, 36 tests, 10 business rules, all pass. `make dbt-ci` exits 0 |
| A3 | Provider sums never exceed national totals; coverage reported | 0 violations | **PASS** (coverage indirect) | `assert_provider_le_national` 0 rows. Coverage reported as "0% of 284 provider-molecule pairs fully observed" (`outputs/benchmark.json`) |
| A4 | Payment mechanics correct | unit tests; reproduction error < $0.01 | **PASS** | `tests/test_mechanics.py` (13) and `tests/test_engine.py` (lag, reference-ASP add-on, IRA 2027Q4 expiry, MA scales revenue). External: parsed 2024 PLs = CMS `Avg_DY24_ASP_Price` for 36 codes, diff 0 |
| A5 | Per-infusion economics from real ASP + PFS + utilization | >= 15 drugs; tornado covers all ranged assumptions | **PASS** | 57 drugs priced; tornado covers every ranged practice assumption, incl. the lesser-of premium (`tests/test_margin.py`) |
| A6 | Forecast backtests with baselines and intervals | >= 5 origins; 80% PI coverage 65-95%; 2025 check reported | **PARTIAL: FAIL for spend** | Selection / decision / test windows; matched comparisons; per-series DM. Test-window coverage: ASP 73-81% by horizon and volume 73-82% (in band); **spend 59-79%, below the 65% floor at h=2** (reported, not tuned). 2025 check: ETS 13.1% vs naive 17.1% |
| A7 | Excel with live formulas matching Python | tabs; >= 100 formulas; no hard-coded numbers; recalc within 0.1% | **PASS** | 1,757 formulas; LibreOffice recalc vs Python under default AND stressed inputs: max rel diff 5.4e-6. Live test runs where LibreOffice exists (CI installs it) |
| A8 | Benchmarking statistically honest | >= 300 providers; 0 cells < 11; intervals | **PASS** (EB removed) | 7,649 clinicians; all exported counts 0 or >= 11; code-grain suppression intervals. EB shrinkage removed because a prior cannot be estimated (ADR 0005) |
| A9 | White-space ranking with weight sensitivity | all counties; >= 1,000 draws | **PASS** | 607 region counties + crossing-metro counties; campus ZIPs mapped (3 of 7,764 specialists unmapped, DQ gate 0.5%); 74 eligible markets; 2,000 draws; mean top-10 overlap 50% |
| A10 | SYNTHETIC RCM labelled; SQL and DAX agree | 100% labelled; 4 KPIs | **PASS** (DAX not executed) | `tests/test_rcm.py` 4 passed; 4 RCM measures mapped to SQL twins |
| A11 | PBIP/TMDL validated | parses; >= 15 measures; description/folder/twin; twin = published | **PASS** (structural only) | `tests/test_tmdl.py` 7 passed: 23 tables, 21 relationships, 25 measures. **Not opened in Power BI Desktop**; DAX never executed |
| A12 | HTML scorecard renders and is screenshotted | >= 3 screenshots; 0 console errors | **PASS** | 6 PNGs, `console_errors: []` |
| A13 | Executive memo | <= 1,000 words; recommendation / risks / what-would-change; numbers traced | **PASS** | `tests/test_memo.py` 4 passed; 925 words |
| A14 | Automation | `make monthly-pack` end to end; `make check` < 3 min | **PASS** | Offline pack OK in 0.6 min, 19 manual steps (~12.2 h, labelled estimate); `make check` ~45 s |
| A15 | README headline numbers match outputs | drift test passes | **PASS** | `tests/test_readme_numbers.py` 3 passed |
| A16 | Plan uses the real 2-quarter lag; lesser-of codes carry a range | payment on ASP(t-2), purchase at ASP(t); range in tornado | **PASS** | `tests/test_engine.py::test_payment_uses_asp_two_quarters_earlier...`; J0129 premium 0-70% in tornado |
| A17 | Formulary-relevant mix, payer-specific, Ohio-calibrated biosimilar shares | listed drugs only; commercial neuro share > Medicare | **PASS** | `tests/test_scenarios.py::test_mix_is_formulary_listed_and_payer_specific` |
| A18 | Demand-driven volume, fixed vs variable cost, chair break-even | operating margin = contribution - fixed; added-chair value computed | **PASS** | base: 1,700 patients -> 7,413 infusions (67%); added chair -$57K at current demand (its fixed cost); break-even 12% |
| A19 | Net collection for every payer | each payer 0.85-1.0 | **PASS** | FFS 95.4%, MA 93.5%, commercial 93.2%, Medicaid 97.0%; pharmacy recapture is its own P&L line and the P&L reconciles |
| A20 | Biosimilar product x payer decision with robustness | one best per molecule x payer; robust flag | **PASS** | `outputs/biosimilar_decision.csv`: 2 of the 12 picks in the plan scenario are robust; insufficient-history picks are never robust |
| A21 | 2028 run-rate consistent, white bagging tiered with IVS recapture | bridge components; recapture monotone | **PASS** | -$580K = white bagging -$566K + IRA -$13K + MFP $0; recapture 0 / 25 / 50% monotone |
| A22 | Forecast selection on validation, scoring on untouched test, DM, decision rule | windows disjoint; decision recorded | **PASS** | Decision window keeps the selected models (7.0% vs 9.2%); test window on 978 matched forecasts: naive 4.8% vs selected 5.2%; per-series DM 1 better / 1 worse of 16 |
| A23 | Sliceable Power BI + budget vs actual with exact bridge + build guide | volume + mix + rate = variance at all grains; guide numbers = kpis | **PASS** | `tests/test_variance.py` 4 passed; pandas re-derivation equals SQL twins |
| A24 | CI regenerates the price path, per-infusion economics and the suite P&L from fixtures | tests pass | **PASS** | `tests/test_regeneration.py` 3 passed (price path and per-infusion economics equal committed outputs exactly) |
