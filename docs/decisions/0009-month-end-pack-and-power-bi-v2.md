# 0009. The month-end pack: budget vs actual, and a sliceable Power BI model

Date: 2026-11-02. Status: accepted.

## Context
A real FP&A pack is budget vs actual, refreshed monthly. Scalar DAX constants and an empty report do not
show that skill. The report pages are built by hand in Power BI Desktop; visual JSON is not authored blind.

## Decision
1. **Budget** = the 2027 plan engine run per site (two illustrative sites in `config/assumptions.yaml`),
   at payer x drug grain, phased by month on operating weekdays (`fact_plan_month`, `fact_fixed_month`).
2. **Actuals** = a SYNTHETIC monthly table for Jan-Mar 2027 (seeded perturbation of volume, payer and
   product mix, and collected revenue). It is labelled in its file name, every row and the model, and is
   used only to demonstrate the method.
3. **Bridge** per site x month at item grain: volume / mix / rate. The three add to the variance exactly
   (tested at total, site and site-month grain).
4. **DAX measures are sliceable** (site, payer, drug, month, scenario). Each has a SQL twin evaluated in a
   stated filter context. This is a **mapping**, not proof the DAX runs. Non-circular checks recompute
   the variance bridge, budget totals and biosimilar share in pandas and compare them with the twins.
5. `docs/powerbi_build_guide.md` (generated) gives a click-by-click build of three pages, with the number
   each visual must show.
6. `make monthly-pack` now produces the month-end pack: refresh, DQ, plan, variance bridge, exports,
   KPIs, Excel, memo, scorecard, README and tests.

## Consequences
The PBIP is still unopened in Power BI Desktop. The first build on Windows should follow the guide and
compare the numbers; a mismatch points at a relationship, a filter context or the DAX.
