# 0010. White-space ranking: what was fixed, and what public data cannot support

Date: 2026-11-02. Status: accepted.

## Fixed
- **Double counting removed.** The Medicare-FFS size z-score correlated 0.98 with market size, so it was
  dropped. The remaining components (size, specialist gap, infusion gap) correlate at |r| <= 0.22.
- **Prescriber floor.** A market needs at least 5 Medicare-billing rheumatologists + neurologists to be
  ranked (Ottawa IL had ranked #3 with ~0).
- **Cross-state metros are scored whole.** Counties of CBSAs that cross into the region are included
  (PLACES pulled for 9 extra states). St. Louis is now MO+IL, Philadelphia PA-NJ-DE-MD, and so on.
- **Naming.** "P(top 10)" is now "share of random weightings in the top 10": it measures robustness to
  weights, not a probability of success.

## Scaled down (not possible with public data)
- **Hospital outpatient infusion pool.** The public hospital outpatient PUF covers only comprehensive
  APCs (no drug-administration APCs), and physician PUF facility rows carry no drug lines. Market-level
  HOPD infusion volume is therefore not public. As a substitute, markets get a context flag
  ("hospital-heavy" = top quartile of acute-care hospitals per 100k, from CMS Hospital General
  Information). The flag is not scored, so a hospital-dense market is not misread as white space.
- **Tuck-in target list** (optional item): not built. Group affiliations would need the CMS Doctors &
  Clinicians file joined at the practice level, and the remaining budget went to the P0/P1 items.

## Result
Northeast Ohio leads among Ohio markets outside the Columbus catchment: Canton-Massillon (#2 of 74, in the
top 10 under 76% of weightings; no Medicare-billing rheumatologists, so a site there means recruiting),
Youngstown (#3), Cleveland (#6, larger base). Detroit ranks #1. The mean top-10 overlap is 51%, so the
ranking is moderately stable, and referral data should outweigh it.
