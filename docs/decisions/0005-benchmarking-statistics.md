# 0005. Benchmarking: suppression-aware, shrunk rates, no names

Date: 2026-11-02. Status: accepted.

## Context
Raw percentile ranks of small-n providers are dominated by noise. A provider with 12 beneficiaries and
a 100% biosimilar rate is not a "top performer". CMS also removes any provider x HCPCS row with fewer
than 11 beneficiaries, which censors the data in a biased direction.

## Decision
1. **Unit** = rendering NPI, peers = same `Rndrng_Prvdr_Type`. Scope = the 7-state region, with the
   national distribution as context.
2. **Biosimilar adoption rate** per multi-source molecule (infliximab, rituximab, tocilizumab,
   natalizumab) = biosimilar beneficiaries / all beneficiaries on that molecule. It is shrunk with
   **empirical-Bayes beta-binomial** (method-of-moments prior per molecule from the peer set):
   posterior mean = (x + a) / (n + a + b), plus 90% credible interval.
3. **Censoring rule**: a provider's molecule rate is only scored when the provider has a visible row
   for that molecule (n >= 11 on at least one code). A missing biosimilar row could mean 0 or 1-10
   beneficiaries. I report how many providers fall in that ambiguous state, and I do not treat it as
   zero.
4. **Continuous KPIs** (Medicare allowed per beneficiary, services per beneficiary, infusion share of
   allowed) are ranked within specialty. Payment per beneficiary is also shown divided by the
   provider's average HCC risk score.
5. **We do not publish any derived cell built from fewer than 11 beneficiaries**, mirroring CMS policy.
   A test enforces this on the exported scorecard.
6. **No names**. Exports carry NPI, specialty, state and county only. The HTML scorecard shows
   aggregate counts only.

## Consequences
Ranks come with intervals. The scorecard labels a provider "above peer" only when its 90% interval
clears the peer median.

## Outcome (build)
99.5% of provider x molecule biosimilar rates are censored: almost every provider shows only one product
row. Only 4 providers clear the "above peer" bar, and 35 the "below peer" bar. Biosimilar adoption is
therefore benchmarked where it is measurable, at **state and national geography level** (infliximab:
Ohio 11.0% vs US 14.1% of in-office administrations, 2024). The provider view is kept, with intervals, as
the method. This is a data limit stated in the README, not a defect to hide.

## Revision 1 (supersedes the shrinkage design above)
Empirical-Bayes shrinkage is removed. With almost no fully observed provider-molecule pair, a prior
cannot be estimated, and the first version silently used a weak fallback prior for every molecule.
Intervals are now built per HCPCS: each eligible code (one with national in-office use that year) that is
missing from a provider's rows hides 0-10 beneficiaries. Codes with no national use are structural zeros
(no denosumab or natalizumab biosimilar existed in 2024). The share is of beneficiary-code pairs, not
de-duplicated patients. Labels are vs the provider's state share, and "insufficient data" applies when the
interval is wider than 0.40. Result: 0% of 284 pairs fully observed; 2 providers above state, 0 below.
The provider view is a method demo, and state-level adoption is the finding.
