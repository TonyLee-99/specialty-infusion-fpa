# 0006. What public data cannot tell us: the illustrative practice and labelled assumptions

Date: 2026-11-02. Status: accepted.

## Context
"How much of our margin comes from infusion" needs the practice's own volumes, payer mix, contracts
and costs. None of these are public. Faking them would break the repo's one hard rule.

## Decision
1. **Real data drives everything that public data can drive**: drug prices (ASP files), Medicare
   payment rules, admin fees (PFS/GPCI), dose per administration and administrations per patient
   (Medicare utilization), drug mix (the Ohio/region neuro+rheum in-office mix in Medicare), the
   regional Medicare drug-vs-medical revenue split (by-Provider file), and Ohio MA penetration (CMS
   enrollment).
2. **What is private becomes an explicit, labelled driver** in `config/assumptions.yaml`. Each entry
   has `value`, `low`, `high`, `source` (a citation) or `label: ASSUMPTION` with the reasoning. The
   drivers are chairs, operating days, chair utilisation, payer mix (commercial / Medicare FFS / MA /
   Medicaid), commercial drug reimbursement vs ASP, coinsurance collection rate, acquisition spread,
   chair-hour cost and nurse ratio.
3. The 2027 plan is run for an **illustrative 12-chair infusion suite** (ASSUMPTION). Results are
   reported as **$ per infusion, % of margin, and sensitivity**, which carry over to any practice
   size. Absolute totals are shown only as an illustration.
4. The tornado chart runs each assumption across its documented low-high range. The memo's
   recommendation must survive the ranges, or the memo has to say which assumption would flip it.

## Consequences
The memo separates "what the public data says" from "what depends on your contracts", and asks the EVP
for the 3 internal numbers that would most change the answer.

## Practice drug mix (build)
The chair mix is the 2024 in-office Medicare FFS administrations billed by rheumatology / neurology /
GI / allergy-immunology clinicians in the 7-state region, infusions only. It is rheum-heavy: abatacept 36%,
golimumab IV 22%, infliximab 20%, tocilizumab 13%. MS infusions (ocrelizumab, natalizumab) are mostly billed in
facility settings or under other provider types, so they are under-represented relative to an MS-heavy site
like Columbus. The per-drug "contribution per chair-hour" table lets the reader re-weight for their own mix.
