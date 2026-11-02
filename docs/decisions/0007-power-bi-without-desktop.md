# 0007. Power BI on a Mac: PBIP/TMDL as text, validated by tests, mirrored in SQL

Date: 2026-11-02. Status: accepted.

## Context
Power BI is the JD's main tool. Power BI Desktop does not run on macOS, and this machine is a Mac.

## Decision
1. Ship a **Power BI Project** (`powerbi/SpecialtyInfusionFPA.pbip`) whose semantic model is authored as
   **TMDL** text: tables over the exported star schema CSVs in `exports/`, relationships, a date table,
   DAX measures with descriptions and display folders.
2. Validate it structurally in `tests/test_tmdl.py`: every file parses, every relationship references
   existing table columns, every measure has a description and a display folder, and **every measure
   has a SQL twin** in `sql/measures/<MeasureName>.sql`.
3. The SQL twins run on DuckDB over the same exports, and their results must equal the published KPI
   values in `outputs/kpis.json`. This shows the DAX logic is the same as the logic that produced the
   README numbers. It does not prove the DAX itself evaluates.
4. A static HTML scorecard (`docs/scorecard.html`) mirrors the intended report pages and is screenshotted
   with Playwright.

## Consequences
**The PBIP has not been opened in Power BI Desktop.** The README and the final report say this plainly.
The first thing to do on a Windows machine is open the .pbip, refresh, and compare the card values to
`outputs/kpis.json`.
