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

## Revision 1: Formulary-relevant mix, demand-driven volume, fixed vs variable
- **Formulary = the operator's published list.** Within each service line, molecule shares come from what
  that line's specialty bills in office nationally (neurologists for neuro, rheumatologists for rheum, four
  specialties for IVIG). Inside a multi-source molecule, the product split is Ohio's 2024 biosimilar share
  (infliximab 11.0%, rituximab 57.4%), placed on the listed biosimilar (Inflectra, Truxima).
- **Payer-specific mix**: the neurology line weight is 40% for Medicare and 60% for commercial and
  Medicaid (assumptions, documented ranges), because MS skews to working age.
- **Volume is demand-driven**: patients x payer share x line weight x within-line share x observed
  administrations per patient-year x demand growth. Chair capacity is only a check; demand above it is
  capped and reported as unmet.
- **Costs**: nurses are fixed (staffed for open hours), as are rent/equipment per chair and site staff.
  Supplies are variable per infusion. This yields the added-chair break-even and the fill-vs-add values.
- The full-formulary variant (adds Orencia, Simponi Aria, Actemra, ...) is kept to size MFP and
  "lesser of" exposure.
