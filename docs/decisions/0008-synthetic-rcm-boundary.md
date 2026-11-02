# 0008. Revenue cycle: a SYNTHETIC method demo, walled off

Date: 2026-11-02. Status: accepted.

## Context
Claim-level AR and denial data (837/835) is private by nature. RCM KPIs are still part of the job: the
JD lists revenue cycle analysis.

## Decision
1. A small generator (`src/sifpa/rcm/generate.py`, seeded) writes 837/835-shaped tables to
   `synthetic/rcm/`. Parameters (denial probabilities by CARC group, payment lags, payer mix) are listed
   in `synthetic/rcm/PARAMETERS.md` and are **invented for illustration**.
2. KPIs (clean-claim rate, denial rate by CARC group, days in AR, net collection rate) are defined once
   in SQL (`sql/rcm/*.sql`) and once in DAX (TMDL `RCM (SYNTHETIC)` display folder).
3. Every output, chart title and table name carries `SYNTHETIC`. **No business conclusion is drawn from
   it**, and the memo does not cite it.
4. A test fails if any file under `synthetic/` or any RCM export lacks the SYNTHETIC label.

## Consequences
The module shows how the KPI logic works and how the DAX/SQL pair is built. It says nothing about
the operator's revenue cycle.
