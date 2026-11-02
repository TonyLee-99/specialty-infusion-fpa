# 0001. A regional operator's public footprint sets the geography and the drug list

Date: 2026-11-02. Status: accepted.

## Context
The repo is written for the EVP of FP&A at a regional inflammatory-disease operator. Everything here is built from public
data. I claim no affiliation and use no internal data. Before choosing a market or a drug list, I read
the operator's public website and press releases (fetched 2026-11-02):

| Fact (public) | Source |
|---|---|
| Founded 2025, private-equity backed. Launched July 30, 2025 by acquiring an MS specialty center (Columbus, OH) and a home infusion / specialty pharmacy (IL) | operator launch press release |
| Clinical focus: inflammatory disease in **neurology, rheumatology and immunology**. Planned ancillaries: infusion, specialty pharmacy, imaging, rehab, nutrition, behavioral health | same release; operator website home page |
| Comprehensive care site: Columbus, OH 43235. Services: infusion and injection, clinical research, specialty visits, spasticity management | operator website |
| In-office infusion drugs listed: Benlysta, Briumvi, Evenity, Gammagard, Gamunex-C, Inflectra, Lemtrada, Ocrevus, Octagam, Prolia, Remicade, Rituxan, Truxima, Tysabri, Vyepti | operator website |
| June 16, 2026: acquired an infusion management-services company (TX). It manages 220+ physician-owned and ambulatory infusion centers nationwide (ID, GI, neuro, rheum, allergy/immunology, pulmonology): drug purchasing, RCM, managed care, staffing | operator acquisition press release |
| Site menu lists states: IL, OH, CA, TX, NV, NJ | operator website navigation |

## Decision
1. **Market region for the white-space analysis = Ohio, plus Illinois (the second owned site and the
   Chicago HQ), plus the states bordering Ohio (IN, KY, MI, PA, WV).** That is 7 states and ~600
   counties. The Columbus comprehensive-care model is the one being replicated. That company's national
   footprint is a management-services business. It is a different growth question and out of scope.
2. **Drug list = the operator's published infusion list, plus the brief's rheum/GI list, plus the
   neurology and immunology biologics a neuro/rheum/immunology practice actually infuses.** The full
   list is in `dbt/seeds/drug_catalog.csv`: molecule, reference vs biosimilar, therapeutic area,
   admin code family. Spasticity management means onabotulinumtoxinA (J0585). It is included because
   Botox was selected for Medicare negotiation (IPAY 2028).
3. **Specialties for benchmarking and supply = Rheumatology, Neurology, Gastroenterology,
   Allergy/Immunology** (Medicare `Rndrng_Prvdr_Type`).

## Consequences
- The memo talks about "a regional inflammatory-disease practice". It never claims to know the operator's own volumes,
  payer mix or contracts.
- I do not profile the operator's own clinicians. Provider scorecards are keyed by NPI with no names, and
  they demonstrate the method on the region's peer set.
