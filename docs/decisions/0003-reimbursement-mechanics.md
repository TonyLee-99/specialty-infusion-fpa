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

## Revision 1 (2026-11-02)
- **The lag is now in the plan, not just in history.** For each 2027 quarter q the engine pays on the ASP
  path at basis quarter q-2 (+6%, or + k x reference ASP for a biosimilar) and costs the purchase at ASP(q)
  (`engine.plan_prices`). The earlier version costed purchases at the lagged basis, so the lag never moved
  the plan. Because the backtests pick naive for 2027 (ADR 0004), the base path is flat and the spread is 0.
  A declining or rising path flows through without code changes (`tests/test_engine.py`).
- **"Lesser of" codes.** Since 2021Q3, J0129 abatacept (and J0717 certolizumab) are paid at 106% of WAC
  because WAC < ASP. PL/1.06 is therefore a LOWER bound on ASP, and calling the old fallback
  "conservative" was wrong. The base buys IV vials at WAC (PL/1.06), a buy-and-bill practice's reference
  price. The tornado range goes up to +70%: J0129's pre-2021Q3 ASP trend (+1.37%/quarter) projected to
  2026Q4 is 70% above today's WAC-based limit. Abatacept is not on the operator's published list, so this
  only bites in the full-formulary variant (up to -$3.96M a year at the extreme).
- **Underwater** now has three nested definitions, each also dollar-weighted: raw PL < ASP;
  0.984 x PL < ASP (sequestration); 0.964 x PL < ASP (plus 90% coinsurance collection). The figures are
  6.2% / 12.0% / 29.8% of drug-quarters (35.9% dollar-weighted).
- **Net collection for every payer**: Medicare FFS 0.8 x 0.98 + 0.2 x coinsurance
  collection, times (1 - denial write-off). MA uses FFS terms x MA rate x (1 - MA denials). Commercial
  nets out patient-responsibility bad debt, denials and underpayment. Medicaid nets out denials.
- **Administration coding.** CGS (Ohio's MAC, J15) instructs that IV abatacept, golimumab, tocilizumab,
  ustekinumab and vedolizumab be billed with 96365-96368, not chemotherapy codes (CGS "Drug
  Administration Coding" article, 2016; may be dated). Other monoclonal antibodies use 96413/96415,
  labelled as an assumption.

## Revision 2: Orencia band and the P&L lines
- **Orencia acquisition band.** The defensible band is WAC +-5%; the general -5%..+3% acquisition spread
  already covers it. The 0.70 premium stays in the tornado only as a **stress bound** (J0129's pre-2021Q3
  ASP trend projected forward). It is not a credible purchase price. In the full-formulary variant:
  - at WAC+5%, operating margin falls from $2.96M to $2.61M;
  - at the stress bound it falls to -$1.97M (a decline of $4.93M, not "a loss of $4.93M").
- **MFP depends on the acquisition basis.** The MFP effect on a full formulary is -$43 when buying at
  WAC, +$64K at WAC+5%, and +$899K at the stress bound, because the refund would then rescue an
  underwater drug. The memo says so.
- **Pharmacy recapture** (Owned-pharmacy margin on white-bagged drug) is now its own P&L line, so drug
  revenue + admin revenue + pharmacy margin - drug cost - variable cost = contribution
  (`tests/test_engine.py`).
