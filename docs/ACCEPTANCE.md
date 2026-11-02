# Acceptance criteria

These criteria were written **before** building (commit 1). Each one ends PASS or FAIL with evidence:
the command, plus an output excerpt. A target that is missed is reported with its real number.

| # | Criterion (measurable) | Target | Status | Evidence |
|---|---|---|---|---|
| A1 | Every source in ADR 0002 is pulled via filtered API or small file, with url/rows/sha256 in `data_manifest.json` | all sources rows > 0; raw total < 3 GB (aim < 500 MB) | TBD | |
| A2 | dbt models + data tests pass on the full warehouse and on CI fixtures | >= 25 tests, >= 4 business-rule tests, 0 failures | TBD | |
| A3 | Suppression-aware reconciliation: provider-level in-office sums never exceed the national total per HCPCS-year; coverage ratio reported | 0 violations | TBD | |
| A4 | Payment mechanics are correct: ASP+6% after sequestration = ASP x 1.04304; published biosimilar PLs are reproduced from implied ASPs | unit tests pass; median abs reproduction error < $0.01 on reproducible rows | TBD | |
| A5 | Per-infusion Medicare economics computed from real ASP + PFS + utilization | >= 15 drugs; tornado covers 100% of ranged assumptions | TBD | |
| A6 | Forecast backtests: rolling origin, baselines, intervals | >= 5 origins; best-model vs naive reported per series; 80% PI empirical coverage on backtest within 65-95%; 2025 out-of-sample error reported | TBD | |
| A7 | Excel scenario workbook with live formulas | Inputs/Calc/Outputs tabs; >= 100 formulas; no hard-coded numbers in Calc/Outputs; LibreOffice-recalculated outputs match Python within 0.1% | TBD | |
| A8 | Provider benchmarking is statistically honest | >= 300 regional providers scored; 0 exported cells < 11 beneficiaries; EB shrinkage applied with intervals | TBD | |
| A9 | White-space ranking with weight sensitivity | every county in 7 states scored; top-10 stability over >= 1,000 random weight draws reported | TBD | |
| A10 | SYNTHETIC RCM layer is labelled and its SQL and DAX agree | 100% of synthetic files/exports labelled; 4 KPIs in SQL and DAX | TBD | |
| A11 | PBIP/TMDL semantic model validated | parses; >= 15 measures; 100% have description, display folder, SQL twin; SQL twin = published KPI (abs diff < 1e-6) | TBD | |
| A12 | HTML scorecard renders and is screenshotted | >= 3 screenshots; 0 console errors | TBD | |
| A13 | Executive memo | <= 2 pages (<= 1,000 words); has recommendation, risks, what-would-change-it; every number comes from outputs JSON (test) | TBD | |
| A14 | Automation | `make monthly-pack` runs end to end and logs the manual steps it replaces; `make check` < 3 min offline | TBD | |
| A15 | README headline numbers match committed outputs | drift test passes | TBD | |
