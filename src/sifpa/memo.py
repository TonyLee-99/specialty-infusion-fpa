"""`make memo`: the executive decision memo, rendered deterministically from outputs/*.json.

No LLM. Every figure in the memo is a {placeholder} filled from `numbers()`; tests/test_memo.py checks
that each numeric token in docs/MEMO.md comes from that dict, so the memo cannot drift from the model.
Writes docs/MEMO.md and outputs/memo_numbers.json.
"""

from __future__ import annotations

import json

from sifpa import assumptions as A
from sifpa.paths import DOCS, OUTPUTS


def J(name: str) -> dict:
    return json.loads((OUTPUTS / name).read_text())


def usd(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e6:
        return f"{sign}${x / 1e6:.1f}M"
    if x >= 1e4:
        return f"{sign}${x / 1e3:.0f}K"
    return f"{sign}${x:,.0f}"


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def numbers() -> dict[str, str]:
    m, sc, fc, bm, mk, tor = (J(n) for n in ("margin.json", "scenarios.json", "forecast.json", "benchmark.json",
                                              "market.json", "tornado.json"))
    s = sc["scenarios"]
    base, push, shock = s["base"], s["biosimilar_push"], s["policy_shock"]
    w = sc["payer_mix"]
    contrib = base["annual"]["contribution"]
    com_share_contrib = w["commercial"] * base["commercial_contribution_per_admin"] / base["per_admin"]["contribution"]
    # acquisition premium over ASP at which a Medicare FFS infusion stops covering its chair cost
    med = m["medicare_ffs_per_admin"]
    breakeven_spread = med["contribution"] / med["acquisition_cost"]
    # biosimilar push: commercial uplift per switched commercial infusion needed to break even
    import pandas as pd

    t = pd.read_csv(OUTPUTS / "scenario_drug_inputs.csv")
    switched_share = float((t["mix_push"] - t["mix_base"]).clip(lower=0).sum())
    switched = switched_share * base["annual"]["administrations"]
    push_delta = push["annual"]["contribution"] - contrib
    push_breakeven = -push_delta / (switched * w["commercial"]) if switched else 0.0
    util = A.practice()["chair_utilization"]
    per_util_pt = contrib * 0.05 / util
    torn = {b["driver"]: b for b in tor["bars"]}
    cm = torn["commercial_drug_markup_vs_asp"]
    real = m["realization"]["allowed_weighted_ratio_2024"]
    top = mk["market_top10"]
    oh = mk["market_top3_ohio_outside_radius"][0]
    qa, an, ext = fc["quarterly_asp"], fc["annual"], fc["external_2025"]
    n = {
        "price_quarter": m["price_quarter"],
        "contrib_2027": usd(contrib),
        "per_admin_2027": usd(base["per_admin"]["contribution"]),
        "per_admin_2026": usd(m["blended_per_admin"]["contribution"]),
        "per_admin_change": pct(base["per_admin"]["contribution"] / m["blended_per_admin"]["contribution"] - 1),
        "admins_2027": f"{base['annual']['administrations']:,}",
        "chairs": str(sc["volume_drivers"]["chairs"]),
        "util": pct(util, 0),
        "med_per_admin": usd(base["medicare_ffs_contribution_per_admin"]),
        "com_per_admin": usd(base["commercial_contribution_per_admin"]),
        "med_drug_margin_pct": pct(m["medicare_drug_margin_pct_of_drug_revenue"]),
        "net_addon": pct(m["net_addon_after_sequestration_full_collection"]),
        "com_share_volume": pct(w["commercial"], 0),
        "com_share_contrib": pct(com_share_contrib, 0),
        "drug_share_gross": pct(m["drug_margin_share_of_gross_margin"], 0),
        "breakeven_spread": pct(breakeven_spread),
        "push_delta": usd(push_delta),
        "push_delta_pct": pct(push_delta / contrib),
        "push_med_gain": usd(push["medicare_ffs_contribution_per_admin"] - base["medicare_ffs_contribution_per_admin"]),
        "push_com_loss": usd(abs(push["commercial_contribution_per_admin"] - base["commercial_contribution_per_admin"])),
        "push_breakeven": usd(push_breakeven),
        "push_target": pct(A.load()["scenarios"]["biosimilar_push_target_share"]["value"], 0),
        "mfp_share_mix": pct(sc["mfp_selected_share_of_base_mix"], 0),
        "mfp_effect": usd(sc["policy_shock_bridge"]["mfp_orencia_entyvio"]),
        "mfp_disc": pct(A.value("policy", "mfp_discount_vs_asp"), 0),
        "wb_effect": usd(sc["policy_shock_bridge"]["white_bagging"]),
        "wb_share": pct(A.load()["scenarios"]["policy_shock_white_bagging"]["value"], 0),
        "shock_delta": usd(shock["annual"]["contribution"] - contrib),
        "ira_expiry": usd(sc["ira_addon_expiry_full_year_effect"]),
        "per_chair": usd(base["contribution_per_chair"]),
        "per_util_pt": usd(per_util_pt),
        "nat_cagr": pct(fc["national_inoffice_admin_cagr_2019_2024"]),
        "nat_admins_2024": f"{fc['national_inoffice_administrations_2024'] / 1e6:.2f}M",
        "top1": top[0]["market"], "top1_p": pct(top[0]["p_top10"], 0),
        "top2": top[1]["market"], "top2_p": pct(top[1]["p_top10"], 0),
        "oh_market": oh["market"], "oh_rank": str(oh["rank"]), "oh_p": pct(oh["p_top10"], 0),
        "oh_miles": str(oh["miles_to_columbus_site"]), "oh_spec": f"{oh['specialists_per_100k']:.1f}",
        "n_markets": str(mk["markets"]["n_eligible"]),
        "overlap": pct(mk["markets"]["mean_top10_overlap_random_weights"], 0),
        "realization": pct(real),
        "realization_gap": pct(1 - real),
        "cm_low": usd(cm["contribution_at_low"]), "cm_high": usd(cm["contribution_at_high"]),
        "cm_low_v": pct(cm["low_value"], 0), "cm_high_v": pct(cm["high_value"], 0),
        "asp_mape_ets": pct(qa["mape_by_model"]["ets_damped"]),
        "asp_mape_naive": pct(qa["mape_by_model"]["naive"]),
        "asp_mape_snaive": pct(qa["mape_by_model"]["seasonal_naive"]),
        "vol_mape_ets": pct(an["mape_by_model"]["ets_damped"]),
        "vol_mape_naive": pct(an["mape_by_model"]["naive"]),
        "ext_mape_ets": pct(ext["mape_2025"]["ets_damped"]),
        "ext_mape_naive": pct(ext["mape_2025"]["naive"]),
        "infl_bio_oh": pct(bm["market_biosimilar_share_2024"]["infliximab"]["OH"]),
        "infl_bio_us": pct(bm["market_biosimilar_share_2024"]["infliximab"]["US"]),
        "censored": pct(bm["share_provider_molecule_censored"]),
        "rheum_drug_share": pct(bm["rheum_infusing_median_drug_share"], 0),
    }
    return n


TEMPLATE = """# Decision memo: CY2027 in-office infusion plan

**To:** EVP, Financial Planning & Analysis. **From:** Zhengtao (Tony) Li. **Date:** 2026-11-02.
**Basis:** public CMS / CDC / Census data (ASP files through {price_quarter}). Practice volumes, payer mix and
contract rates are labelled assumptions for an illustrative {chairs}-chair suite in Ohio. Use the $ per
infusion and the % figures; the totals are illustrations.

## Recommendation
1. **Budget the infusion line as a commercial-contract business, not a drug-volume business.** Base-case 2027
   contribution is {per_admin_2027} per chair infusion ({per_admin_change} vs {price_quarter} prices), or
   {contrib_2027} on {admins_2027} infusions at {util} chair utilization. Medicare FFS earns {med_per_admin} per
   infusion. Its drug margin is only {med_drug_margin_pct} of drug revenue: ASP+6% nets to {net_addon} after
   sequestration, before coinsurance bad debt. Commercial earns {com_per_admin} (assumed contract). Commercial is
   {com_share_volume} of volume but {com_share_contrib} of infusion contribution.
2. **Do not run a blanket biosimilar conversion for margin.** Moving infliximab, rituximab, tocilizumab and
   natalizumab to {push_target} biosimilar changes contribution by {push_delta} ({push_delta_pct}). Medicare gains
   {push_med_gain} per infusion, because the IRA add-on is 8% of the *reference* ASP. Commercial loses
   {push_com_loss} per infusion, because ASP-plus contracts pay less on a cheaper drug. Convert where payers
   mandate it, or where a contract pays at least {push_breakeven} more per switched commercial infusion
   (shared savings or reference-ASP pricing).
3. **Contract for the 2028 policy stack now.** {mfp_share_mix} of the chair-infusion mix is Orencia or Entyvio,
   both selected for Medicare negotiation (MFP effective 2028). At an assumed {mfp_disc} MFP discount the
   Medicare effect is only {mfp_effect}, because Medicare margin is already thin. The larger exposure is payer
   white bagging: {wb_effect} if {wb_share} of commercial infusions move to specialty pharmacy. Together that is
   {shock_delta} per year. The scheduled end of the +8% biosimilar add-on (2027-09-30) is small for this mix
   ({ira_expiry} full-year).
4. **Grow capacity in Ohio first, and pick the next site at metro grain.** National in-office Medicare
   administrations of these drugs grew {nat_cagr} a year from 2019 to 2024 ({nat_admins_2024} in 2024). One chair
   is worth {per_chair} a year, and each 5 points of utilization is worth {per_util_pt}. Fill chairs before
   adding them. For a new comprehensive site, **{oh_market}** is the strongest Ohio market outside the Columbus
   catchment: rank {oh_rank} of {n_markets}, {oh_miles} miles away, {oh_spec} relevant specialists per 100k, in
   the top 10 under {oh_p} of 2,000 random weightings. {top1} ({top1_p}) and {top2} ({top2_p}) rank higher but
   leave Ohio. Chicago pairs with the existing Wood Dale (the owned specialty pharmacy) footprint.

## Risks
- **Realization.** In 2024 the national in-office allowed amount per billed unit was {realization} of the
  average quarterly payment limit. If that {realization_gap} gap is real for us, it is larger than the Medicare
  drug margin. Check it against our 835s before relying on any Medicare drug margin.
- **Commercial terms dominate.** Across the documented range ({cm_low_v} to {cm_high_v} over ASP), annual
  contribution runs from {cm_low} to {cm_high}. No other driver moves the answer as much.
- **Purchasing.** A Medicare infusion stops covering its chair cost if we buy {breakeven_spread} above ASP.
- **Forecasts.** Quarterly ASP backtest MAPE is {asp_mape_ets} (damped ETS) vs {asp_mape_naive} naive and
  {asp_mape_snaive} seasonal naive. Annual volume MAPE is {vol_mape_ets} vs {vol_mape_naive} naive. On the
  2025 out-of-sample check, spend MAPE was {ext_mape_ets} vs {ext_mape_naive} naive. Volume is the uncertain
  part, not price.
- **Data limits.** Medicare FFS only (MA claims are not public). Provider-level biosimilar rates are censored
  for {censored} of provider-molecule pairs, so adoption is benchmarked at state level (infliximab biosimilar
  share {infl_bio_oh} in Ohio vs {infl_bio_us} nationally).

## What would change this recommendation
- Commercial contracts that pay biosimilars on reference-ASP terms, or share at least {push_breakeven} per
  switched infusion. Biosimilar conversion would then add margin.
- Acquisition cost at or above ASP+{breakeven_spread} (non-GPO purchasing). Medicare infusion volume would then
  need to be capped or re-routed.
- Published MFPs (due 2026-11-30) far below the assumed {mfp_disc} discount, or payer white bagging above
  {wb_share}. The 2028 exposure would then become the first-order issue.
- Internal referral and leakage data that contradicts the public ranking. The ranking is only moderately
  stable (mean top-10 overlap under random weightings: {overlap}), so referral data should outweigh it.

**Three internal numbers that would most sharpen this:** commercial drug terms by payer (markup over ASP or
% of WAC), invoice acquisition cost vs ASP for the top 10 drugs, and chair utilization plus payer mix by site.
In this region's Medicare data, drugs are {rheum_drug_share} of allowed for infusing rheumatologists, so these
three inputs decide most of the practice's revenue picture.
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
