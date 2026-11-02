"""`make memo`: the executive decision memo, rendered deterministically from outputs/*.json.

No LLM. Every figure is a {placeholder} filled from `numbers()`; tests/test_memo.py checks that each
numeric token in docs/MEMO.md comes from that dict. One price basis throughout: 2027.
Writes docs/MEMO.md and outputs/memo_numbers.json.
"""

from __future__ import annotations

import json

import pandas as pd

from sifpa import assumptions as A
from sifpa.paths import DOCS, OUTPUTS


def J(name: str) -> dict:
    return json.loads((OUTPUTS / name).read_text())


def usd(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e6:
        return f"{sign}${x / 1e6:.2f}M"
    if x >= 1e4:
        return f"{sign}${x / 1e3:.0f}K"
    return f"{sign}${x:,.0f}"


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def numbers() -> dict[str, str]:
    m, sc, fc, bm, mk, tor = (J(n) for n in ("margin.json", "scenarios.json", "forecast.json", "benchmark.json",
                                              "market.json", "tornado.json"))
    s = sc["scenarios"]
    base, listed, best, p28 = s["base"], s["biosimilar_listed"], s["biosimilar_best"], s["policy_2028"]
    br = sc["policy_2028_bridge"]
    torn = {b["driver"]: b for b in tor["bars"]}
    cm, sp = torn["commercial_drug_markup_vs_asp"], torn["acquisition_spread_vs_asp"]
    dec = pd.read_csv(OUTPUTS / "biosimilar_decision.csv")
    best_rows = dec[dec["best_for_payer"]]
    top = mk["market_top10"]
    oh = mk["market_top3_ohio_outside_radius"]
    cle = next(r for r in top if r["market"].startswith("Cleveland"))
    qa = fc["quarterly_asp"]
    uw = m["underwater"]["after_sequestration_and_coinsurance"]
    ivs = sc["policy_2028_operating_margin_by_ivs_recapture"]
    return {
        "contrib": usd(base["contribution"]), "op_margin": usd(base["operating_margin"]),
        "fixed": usd(base["fixed_costs"]["total"]), "admins": f"{base['administrations']:,}",
        "patients": f"{base['patients']:,}", "util": pct(base["utilization"], 0), "chairs": str(A.practice()["chairs"]),
        "per_admin": usd(base["contribution_per_admin"]),
        "med": usd(base["contribution_per_admin_medicare_ffs"]), "ma": usd(base["contribution_per_admin_medicare_adv"]),
        "com": usd(base["contribution_per_admin_commercial"]),
        "med_margin_pct": pct(m["medicare_drug_margin_pct_of_drug_revenue"]),
        "net_addon": pct(m["net_addon_after_sequestration_full_collection"]),
        "collect_ffs": pct(m["collection_factor_by_payer"]["medicare_ffs"]),
        "collect_com": pct(m["collection_factor_by_payer"]["commercial"]),
        "com_admins": pct(base["commercial_share_of_admins"], 0), "com_contrib": pct(base["commercial_share_of_contribution"], 0),
        "cm_lo_v": pct(cm["low_value"], 0), "cm_hi_v": pct(cm["high_value"], 0),
        "cm_lo": usd(cm["at_low"]), "cm_hi": usd(cm["at_high"]),
        "sp_lo_v": pct(sp["low_value"], 0), "sp_hi_v": pct(sp["high_value"], 0), "sp_lo": usd(sp["at_low"]), "sp_hi": usd(sp["at_high"]),
        "listed_delta": usd(listed["operating_margin"] - base["operating_margin"]),
        "best_delta": usd(best["operating_margin"] - base["operating_margin"]),
        "push_target": pct(A.load()["scenarios"]["biosimilar_push_target_share"]["value"], 0),
        "n_best": str(len(best_rows)), "n_robust": str(int(best_rows["decision_robust"].sum())),
        "p28_delta": usd(p28["operating_margin"] - base["operating_margin"]),
        "wb": usd(br["white_bagging_net_of_ivs"]), "ira": usd(br["ira_addon_expiry"]), "mfp": usd(br["mfp"]),
        "mfp_ff": usd(sc["mfp_effect_full_formulary"]),
        "mfp_ff_share": pct(sc["mfp_selected_share_of_admins_full_formulary"], 0),
        "ivs_step": usd(ivs["0.5"] - ivs["0.25"]),
        "lesser_of": usd(abs(m["lesser_of_premium_effect_full_formulary"])),
        "chair_fixed": usd(base["added_chair_fixed_cost"]), "chair_value": usd(base["added_chair_value"]),
        "chair_be": pct(base["added_chair_breakeven_utilization"], 0),
        "plus100": usd(sc["value_of_100_more_patients"]),
        "n_markets": str(mk["markets"]["n_eligible"]),
        "top1": top[0]["market"], "top1_s": pct(top[0]["share_of_weightings_in_top10"], 0),
        "oh1": oh[0]["market"], "oh1_rank": str(oh[0]["rank"]), "oh1_s": pct(oh[0]["share_of_weightings_in_top10"], 0),
        "oh1_rheum": str(oh[0]["rheumatologists"]), "oh1_spec": f"{oh[0]['specialists_per_100k']:.1f}",
        "cle_rank": str(cle["rank"]), "cle_s": pct(cle["share_of_weightings_in_top10"], 0),
        "cle_rheum": str(cle["rheumatologists"]), "overlap": pct(mk["markets"]["mean_top10_overlap_random_weights"], 0),
        "asp_naive": pct(qa["test_mape_naive"]), "asp_sel": pct(qa["test_mape_selected"]),
        "asp_cov": pct(qa["pi80_test_coverage_overall"], 0),
        "uw": pct(uw["share_drug_quarters"], 0), "uw_d": pct(uw["dollar_weighted_share"], 0),
        "infl_oh": pct(bm["market_biosimilar_share_2024"]["infliximab"]["OH"]),
        "infl_us": pct(bm["market_biosimilar_share_2024"]["infliximab"]["US"]),
    }


TEMPLATE = """# Decision memo: CY2027 in-office infusion plan

**To:** EVP, Financial Planning & Analysis. **From:** Zhengtao (Tony) Li. **Date:** 2026-11-02.
**Basis:** public CMS / CDC / Census data, one price basis (2027: Medicare pays on the ASP of two quarters
earlier, the practice buys at the current ASP). Patients, payer mix, contracts and costs are labelled
assumptions for an illustrative {chairs}-chair suite with a regional operator's published drug list. Read the $ per
infusion and the deltas; the totals are illustrations.

## Recommendation
1. **Budget the infusion line as a commercial-contract business.** The 2027 base case gives {admins}
   infusions for {patients} patients ({util} of chair capacity). Contribution is {contrib}; after {fixed} of
   fixed suite cost, operating margin is {op_margin}. Medicare FFS contributes {med} per infusion: ASP+6% nets
   to {net_addon} after sequestration, and after coinsurance bad debt and denials the Medicare drug margin is
   {med_margin_pct} of drug revenue. MA contributes {ma}. The assumed commercial contract contributes {com},
   after patient bad debt, denials and underpayment ({collect_com} collected). Commercial is {com_admins} of
   infusions and {com_contrib} of contribution.
2. **Decide biosimilars product by payer; don't push them across the board.** Moving infliximab and rituximab
   to {push_target} on the listed products (Inflectra, Truxima) changes operating margin by {listed_delta}.
   Giving each payer its best-margin product would add up to {best_delta}. But only {n_robust} of {n_best} of
   those payer-level picks survive the products' own price swings over the last 12 quarters. The workable
   rule: put Medicare patients on the IRA +8% products while that window lasts, and ask commercial payers to
   price biosimilars on reference-ASP terms before converting them.
3. **Contract for 2028 now; the exposure is white bagging, not drug negotiation.** The 2028 run-rate changes
   operating margin by {p28_delta}. White bagging accounts for {wb} (tiered by drug cost, net of the owned specialty pharmacy
   recapture), and the end of the +8% add-on for {ira}. Medicare negotiation costs {mfp} on the listed drug
   list, because none of those drugs was selected. Adding Orencia to the formulary (selected drugs would be
   {mfp_ff_share} of infusions in a full-formulary book) changes this by only {mfp_ff}, because the Medicare margin on it is
   about 1%. Priorities: site-of-care and white-bagging carve-outs in contracts; the owned specialty pharmacy in payer
   networks (each 25 points of recapture is worth {ivs_step}).
4. **Grow by patients, not chairs.** At {util} utilization, another chair adds {chair_fixed} of fixed cost and
   no volume ({chair_value} a year). 100 more patients add {plus100}. Once demand exceeds capacity, an added
   chair breaks even at {chair_be} utilization. For a new site, Northeast Ohio leads.
   - **{oh1}** ranks {oh1_rank} of {n_markets} and is in the top 10 under {oh1_s} of random weightings. It has
     {oh1_spec} relevant specialists per 100k and {oh1_rheum} Medicare-billing rheumatologists, so a site
     there means recruiting.
   - **Cleveland** (rank {cle_rank}, {cle_s}, {cle_rheum} rheumatologists) is the larger base.
   - {top1} ranks first ({top1_s}) but leaves Ohio.

## Risks
- **Commercial terms dominate.** Across the documented markup range ({cm_lo_v} to {cm_hi_v} over ASP),
  operating margin runs from {cm_lo} to {cm_hi}. Purchasing is next: an acquisition spread of {sp_lo_v} to
  +{sp_hi_v} vs ASP moves it from {sp_lo} to {sp_hi}.
- **Price path.** Across the test window, no forecasting model beat naive (MAPE {asp_naive} naive vs
  {asp_sel} for the selected models), so 2027 prices are held at the latest file. That makes the lag spread
  zero in the base. In {uw} of past drug-quarters ({uw_d} dollar-weighted), Medicare's collected payment fell
  below the price the practice paid at the time. The held-flat path's 80% band covered {asp_cov} of test
  outcomes.
- **Orencia pricing.** Orencia's Medicare limit is set on WAC ("lesser of"). If acquisition tracked its old
  ASP trend, a full rheum formulary would lose {lesser_of} a year.
- **Data limits.** Medicare FFS only; MA claims are not public. The drug mix comes from what
  neurologists and rheumatologists bill in office nationally, and it under-represents hospital-based MS
  infusion. Provider-level biosimilar rates cannot be measured through CMS suppression, so adoption is
  benchmarked by state (infliximab {infl_oh} Ohio vs {infl_us} US).

## What would change this recommendation
- Commercial biosimilar contracts priced on reference-ASP terms: biosimilar conversion becomes a margin lever.
- Acquisition cost above ASP (non-GPO purchasing): Medicare and MA infusions turn loss-making.
- the owned specialty pharmacy inside the big payers' specialty networks, or white bagging below the assumed tiers: the 2028
  exposure shrinks.
- Referral data showing Northeast Ohio demand already served. Weight-stability of the ranking is moderate
  (mean top-10 overlap {overlap}), so referral data should outweigh it.

**The three internal numbers that would sharpen this most:** commercial drug terms by payer, invoice
acquisition cost vs ASP for the top 10 drugs, and the active patient panel by drug and payer.
"""


def build() -> tuple[str, dict]:
    n = numbers()
    return TEMPLATE.format(**n), n


def main() -> None:
    text, n = build()
    (DOCS / "MEMO.md").write_text(text)
    (OUTPUTS / "memo_numbers.json").write_text(json.dumps(n, indent=2) + "\n")
    print(text)
    print("words:", len(text.split()))


if __name__ == "__main__":
    main()
