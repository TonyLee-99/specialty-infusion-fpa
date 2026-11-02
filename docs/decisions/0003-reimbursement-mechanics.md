# 0003. Buy-and-bill mechanics and the acquisition-cost proxy

Date: 2026-11-02. Status: accepted.

## Context
In-office infusion margin under Medicare FFS has three parts: the drug add-on, the administration fee,
and the cost of the drug and the chair. True acquisition cost (GPO contract price, rebates, prompt-pay
discounts) is private. I need a defensible public proxy, and I need to be explicit about what it
leaves out.

## Decision (implemented in `src/sifpa/mechanics.py`, unit-tested in `tests/test_mechanics.py`)
1. **Payment limit (PL) for quarter t = 1.06 x ASP(t-2)** for single-source and reference products.
   The ASP file for quarter t is built from manufacturer sales two quarters earlier ("based on 2Q26 ASP
   data" for the Oct-2026 file).
2. **Biosimilar PL = ASP_bio(t-2) + k x ASP_ref(t-2)**, with k = 8% while the IRA s.11403 window applies
   (the file note says `8% of reference add-on applied`) and 6% otherwise. The add-on is computed on the
   *reference* product's ASP. So a cheaper biosimilar earns the same add-on dollars as the reference.
3. **Implied ASP** is backed out from published PLs. For reference products, ASP(t-2) = PL(t)/1.06. For
   biosimilars, ASP_bio = PL_bio - k x ASP_ref, using the reference PL from the same file. Rows
   flagged `"lesser of"` or `AMP-based` are excluded from implied-ASP math, because their PL is not
   ASP-based.
4. **Sequestration**: Medicare's 80% share is cut 2%. The provider collects 0.8 x 0.98 + 0.2 x c of
   allowed, where c = the coinsurance collection rate (assumption, `config/assumptions.yaml`). With
   c = 1, ASP+6% nets to ASP x 1.06 x 0.984 = **ASP + 4.3%**.
5. **Acquisition-cost proxy = the ASP of the quarter the drug is bought, x (1 + spread)**. The spread
   defaults to 0% and runs -5%..+3% in sensitivity. ASP is a volume-weighted average net price, so
   roughly half of purchasers pay more and half pay less. Because payment lags by two quarters, the
   **lag spread** is PL(t) - ASP(t) = 1.06 x ASP(t-2) - ASP(t). I compute it from real files for every
   drug and quarter. It is positive when prices fall (biosimilar erosion) and negative when list prices
   rise ("underwater" risk).
6. **Administration fee** = PFS non-facility payment = (wRVU x PW + PE x PE_GPCI + MP x MP_GPCI) x CF,
   with Ohio's statewide GPCI. Admin code family per drug: monoclonal antibodies use the 96413 + 96415
   per additional hour family; IVIG and the others use 96365 + 96366; subcutaneous and IM injections
   use 96372. **MACs differ on 96413 vs 96365 for some biologics, so this is labelled an assumption.**
   Infusion hours come from the FDA label, per drug, in `config/assumptions.yaml`.
7. **Dose per administration is observed, not assumed**: units per beneficiary-day =
   Tot_Srvcs / Tot_Bene_Day_Srvcs from 2024 in-office national Medicare data. Administrations per
   beneficiary per year = Tot_Bene_Day_Srvcs / Tot_Benes.

## What this leaves out (stated in README limitations)
GPO and 340B pricing, manufacturer rebates, discarded-drug (JW/JZ) refunds, inflation-rebate coinsurance
adjustments (provider total payment is unchanged), bad debt beyond the coinsurance assumption,
commercial contract rates (assumption only), and MA plan rates (assumed equal to FFS, labelled).

## Validation results (build, 2026-11-02)
- **Parsing is exact.** The mean of our four parsed 2024 quarterly PLs equals CMS's own `Avg_DY24_ASP_Price`
  (Part B Spending by Drug, an independent CMS product) for all 36 catalog codes present in both (dbt test
  `assert_asp_parse_matches_cms_dy24`, tolerance 0.1%; observed difference 0).
- **Qualifying-biosimilar rule holds**: every row flagged `8% of reference add-on applied` has implied
  ASP <= reference ASP, once ustekinumab biosimilars (ambiguous reference) are excluded.
- **Realization gap (open question).** National in-office allowed per billed unit in 2024 was 96.8% of the
  year's mean PL (allowed-weighted, 36 codes). Alemtuzumab, Gammaplex and ublituximab sit below 90% (`make dq`
  flags them). Candidate causes: unit-billing artifacts, MSP/secondary-payer lines, and allowed reduced to a
  lower submitted charge. The gap is **not** assumed away. It is a downside bar in the tornado and a memo risk.
- CMS PUF `Avg_Mdcr_Pymt_Amt` is **before sequestration** (payment/allowed ~0.79 nationally, not 0.784), so
  the dbt payment rule tests the [0.75, 0.81] band.
