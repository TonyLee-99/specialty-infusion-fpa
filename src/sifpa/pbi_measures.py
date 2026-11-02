"""DAX measures of the semantic model, each with a SQL twin evaluated in ONE stated filter context.

Entry: (table, measure, DAX, display folder, format, description, context, SQL twin).
The DAX is written to be sliceable (site / payer / drug / month / scenario); the SQL twin reproduces the
measure in the stated context only. This is a measure-to-SQL MAPPING, not proof the DAX evaluates:
the DAX has never run (no Power BI Desktop on this Mac, ADR 0007). What IS checked independently:
tests/test_tmdl.py recomputes several twins in pandas (variance bridge, budget totals, biosimilar share)
and against the analysis outputs, so the SQL is not checked against itself.
"""

from __future__ import annotations

import re

PCT, INT, CUR, DEC = "0.0%", "#,##0", "\\$#,##0", "#,##0.00"
_ACT = "fact_actual_month_SYNTHETIC"
_M = f"VAR m = MAX ( {_ACT}[month_start] )"
_BUD_TO_M = "CALCULATE ( SUM ( fact_plan_month[{c}] ), fact_plan_month[month_start] <= m )"
_SQL_ACT_MAX = f"(select max(month_start) from {_ACT})"
S1 = "site_id = 'S1'"

MEASURES = [
    # ---------------- Pricing (ASP files) ----------------
    ("fact_asp_quarter", "Median Lag Spread %", "MEDIAN ( fact_asp_quarter[lag_spread_pct] )",
     "Pricing", PCT, "Median of payment limit / current-quarter ASP - 1 (what the 2-quarter lag pays above today's price).",
     "all drugs, all quarters", "select median(lag_spread_pct) from fact_asp_quarter where lag_spread_pct is not null"),
    ("fact_asp_quarter", "Underwater Share After Sequestration and Coinsurance",
     "DIVIDE ( COUNTROWS ( FILTER ( fact_asp_quarter, fact_asp_quarter[payment_limit] * 0.964 < fact_asp_quarter[asp_current] ) ), "
     "COUNTROWS ( FILTER ( fact_asp_quarter, NOT ISBLANK ( fact_asp_quarter[asp_current] ) ) ) )",
     "Pricing", PCT, "Share of drug-quarters where Medicare's collected payment (0.8 x 0.98 + 0.2 x 0.90 of PL) is below the current ASP.",
     "all drugs, all quarters",
     "select avg(case when payment_limit * 0.964 < asp_current then 1.0 else 0.0 end) from fact_asp_quarter where asp_current is not null"),
    # ---------------- Utilization (national Medicare FFS) ----------------
    ("fact_national_drug_year", "In-Office Chair Infusions",
     "CALCULATE ( SUM ( fact_national_drug_year[bene_day_services] ), fact_national_drug_year[place_of_service] = \"O\", "
     "dim_drug[admin_family] IN { \"mab_infusion\", \"iv_infusion\" } )",
     "Utilization", INT, "National Medicare FFS in-office chair infusions (beneficiary-days) of catalog drugs; slice by year / molecule.",
     "year = 2024",
     "select sum(n.bene_day_services) from fact_national_drug_year n join dim_drug d using (hcpcs) "
     "where n.year = 2024 and n.place_of_service = 'O' and d.admin_family in ('mab_infusion', 'iv_infusion')"),
    ("fact_national_drug_year", "Biosimilar Share of Administrations",
     "VAR o = CALCULATE ( SUM ( fact_national_drug_year[bene_day_services] ), fact_national_drug_year[place_of_service] = \"O\" ) "
     "RETURN DIVIDE ( CALCULATE ( SUM ( fact_national_drug_year[bene_day_services] ), fact_national_drug_year[place_of_service] = \"O\", "
     "dim_drug[is_biosimilar] = TRUE () ), o )",
     "Utilization", PCT, "Biosimilar share of in-office administrations; slice by molecule and year.",
     "molecule = infliximab, year = 2024",
     "select sum(case when d.is_biosimilar then n.bene_day_services else 0 end) / sum(n.bene_day_services) "
     "from fact_national_drug_year n join dim_drug d using (hcpcs) where n.year = 2024 and n.place_of_service = 'O' and d.molecule = 'infliximab'"),
    # ---------------- Budget (2027 plan by site x month x payer x drug) ----------------
    ("fact_plan_month", "Budget Contribution", "SUM ( fact_plan_month[contribution] )",
     "Budget", CUR, "2027 plan contribution (revenue collected - drug cost - variable cost); slice by site, payer, drug, month.",
     "site S1, full year", f"select sum(contribution) from fact_plan_month where {S1}"),
    ("fact_plan_month", "Budget Administrations", "SUM ( fact_plan_month[admins] )",
     "Budget", INT, "2027 planned chair infusions (demand-driven).", "site S1, full year",
     f"select sum(admins) from fact_plan_month where {S1}"),
    ("fact_plan_month", "Budget Contribution per Admin", "DIVIDE ( [Budget Contribution], [Budget Administrations] )",
     "Budget", CUR, "Plan contribution per infusion.", "payer = commercial, site S1",
     f"select sum(contribution) / sum(admins) from fact_plan_month where {S1} and payer = 'commercial'"),
    ("fact_fixed_month", "Budget Fixed Costs", "SUM ( fact_fixed_month[fixed_total] )",
     "Budget", CUR, "Nursing for open hours, rent/equipment per chair, site staff.", "site S1, full year",
     f"select sum(fixed_total) from fact_fixed_month where {S1}"),
    ("fact_plan_month", "Budget Operating Margin", "[Budget Contribution] - [Budget Fixed Costs]",
     "Budget", CUR, "Contribution after fixed suite costs.", "site S1, full year",
     f"select (select sum(contribution) from fact_plan_month where {S1}) - (select sum(fixed_total) from fact_fixed_month where {S1})"),
    # ---------------- Variance (SYNTHETIC actuals) ----------------
    (_ACT, "Actual Contribution (SYNTHETIC)", f"SUM ( {_ACT}[contribution] )",
     "Variance (SYNTHETIC)", CUR, "SYNTHETIC actual contribution (method demo).", "site S1, months closed",
     f"select sum(contribution) from {_ACT} where {S1}"),
    (_ACT, "Budget Contribution to Date",
     f"{_M} RETURN " + _BUD_TO_M.format(c="contribution"),
     "Variance (SYNTHETIC)", CUR, "Budget contribution over the months that have (SYNTHETIC) actuals; the waterfall's starting bar.",
     "site S1, months closed",
     f"select sum(contribution) from fact_plan_month where {S1} and month_start <= {_SQL_ACT_MAX}"),
    (_ACT, "Contribution Variance (SYNTHETIC)",
     f"{_M} RETURN [Actual Contribution (SYNTHETIC)] - " + _BUD_TO_M.format(c="contribution"),
     "Variance (SYNTHETIC)", CUR, "Actual - budget over the months closed (SYNTHETIC actuals).", "site S1, months closed",
     f"select (select sum(contribution) from {_ACT} where {S1}) - (select sum(contribution) from fact_plan_month "
     f"where {S1} and month_start <= {_SQL_ACT_MAX})"),
    (_ACT, "Volume Variance (SYNTHETIC)",
     f"{_M} VAR ba = " + _BUD_TO_M.format(c="admins") + " VAR bc = " + _BUD_TO_M.format(c="contribution")
     + f" RETURN ( SUM ( {_ACT}[admins] ) - ba ) * DIVIDE ( bc, ba )",
     "Variance (SYNTHETIC)", CUR, "Change in administrations at budget contribution per administration.", "site S1, months closed",
     f"with b as (select sum(admins) ba, sum(contribution) bc from fact_plan_month where {S1} and month_start <= {_SQL_ACT_MAX}), "
     f"a as (select sum(admins) aa from {_ACT} where {S1}) select (aa - ba) * bc / ba from a, b"),
    (_ACT, "Mix Variance (SYNTHETIC)",
     f"{_M} VAR ba = " + _BUD_TO_M.format(c="admins") + f" VAR aa = SUM ( {_ACT}[admins] ) RETURN SUMX ( VALUES ( dim_item[item_key] ), "
     "VAR bi = " + _BUD_TO_M.format(c="admins") + " VAR bc = " + _BUD_TO_M.format(c="contribution")
     + f" VAR ai = CALCULATE ( SUM ( {_ACT}[admins] ) ) RETURN ( ai - aa * DIVIDE ( bi, ba ) ) * DIVIDE ( bc, bi ) )",
     "Variance (SYNTHETIC)", CUR, "Change in payer x drug mix at budget unit contribution.", "site S1, months closed",
     f"with b as (select item_key, sum(admins) bi, sum(contribution) bc from fact_plan_month where {S1} and month_start <= {_SQL_ACT_MAX} group by 1), "
     f"a as (select item_key, sum(admins) ai from {_ACT} where {S1} group by 1), "
     "t as (select (select sum(bi) from b) ba, (select sum(ai) from a) aa) "
     "select sum((coalesce(a.ai, 0) - t.aa * b.bi / t.ba) * b.bc / b.bi) from b left join a using (item_key), t"),
    (_ACT, "Rate Variance (SYNTHETIC)",
     f"{_M} RETURN SUMX ( VALUES ( dim_item[item_key] ), VAR bi = " + _BUD_TO_M.format(c="admins") + " VAR bc = "
     + _BUD_TO_M.format(c="contribution") + f" VAR ai = CALCULATE ( SUM ( {_ACT}[admins] ) ) VAR ac = CALCULATE ( SUM ( {_ACT}[contribution] ) ) "
     "RETURN ai * ( DIVIDE ( ac, ai ) - DIVIDE ( bc, bi ) ) )",
     "Variance (SYNTHETIC)", CUR, "Change in contribution per administration (prices, collections, drug cost).", "site S1, months closed",
     f"with b as (select item_key, sum(admins) bi, sum(contribution) bc from fact_plan_month where {S1} and month_start <= {_SQL_ACT_MAX} group by 1), "
     f"a as (select item_key, sum(admins) ai, sum(contribution) ac from {_ACT} where {S1} group by 1) "
     "select sum(a.ai * (a.ac / a.ai - coalesce(b.bc / b.bi, 0))) from a left join b using (item_key)"),
    # ---------------- Scenarios ----------------
    ("fact_scenarios", "Scenario Contribution",
     "CALCULATE ( SUM ( fact_scenarios[value] ), fact_scenarios[metric] = \"contribution\" )",
     "Scenarios", CUR, "Annual contribution of the 12-chair suite; use fact_scenarios[scenario] as a slicer.",
     "scenario = policy_2028", "select sum(value) from fact_scenarios where scenario = 'policy_2028' and metric = 'contribution'"),
    # ---------------- Benchmark ----------------
    ("fact_provider_scorecard", "Providers Scored", "COUNTROWS ( fact_provider_scorecard )",
     "Benchmark", INT, "Region rheum / neuro / GI / allergy clinicians with >= 11 Medicare beneficiaries (2024).",
     "all", "select count(*) from fact_provider_scorecard"),
    ("fact_provider_scorecard", "Median Allowed per Beneficiary", "MEDIAN ( fact_provider_scorecard[allowed_per_bene] )",
     "Benchmark", CUR, "Median Medicare allowed per beneficiary; slice by specialty for the peer view.",
     "provider_type = Rheumatology", "select median(allowed_per_bene) from fact_provider_scorecard where provider_type = 'Rheumatology'"),
    ("fact_provider_scorecard", "Providers Below State on Biosimilars",
     "COUNTROWS ( FILTER ( fact_provider_scorecard, fact_provider_scorecard[biosimilar_vs_state] = \"below_state\" ) )",
     "Benchmark", INT, "Providers whose whole suppression-aware interval sits below their state's biosimilar share.",
     "all", "select count(*) from fact_provider_scorecard where biosimilar_vs_state = 'below_state'"),
    # ---------------- Market ----------------
    ("dim_market", "Eligible Markets", "COUNTROWS ( FILTER ( dim_market, dim_market[eligible] = TRUE () ) )",
     "Market", INT, "Markets above the population and prescriber floors.", "all", "select count(*) from dim_market where eligible"),
    ("dim_market", "Share of Weightings in Top 10",
     "MAX ( dim_market[share_of_weightings_in_top10] )",
     "Market", PCT, "Share of 2,000 random weightings in which a market ranks in the top 10; select one market.",
     "market = Canton-Massillon, OH", "select share_of_weightings_in_top10 from dim_market where market_name = 'Canton-Massillon, OH'"),
    # ---------------- RCM (SYNTHETIC) ----------------
    ("fact_rcm_remits_SYNTHETIC", "Denial Rate (SYNTHETIC)",
     "CALCULATE ( DIVIDE ( COUNTROWS ( FILTER ( fact_rcm_remits_SYNTHETIC, fact_rcm_remits_SYNTHETIC[denied] = TRUE () ) ), "
     "COUNTROWS ( fact_rcm_remits_SYNTHETIC ) ), fact_rcm_remits_SYNTHETIC[remit_seq] = 1 )",
     "RCM (SYNTHETIC)", PCT, "SYNTHETIC demo: initial denials / first remits.", "all",
     "select avg(case when denied then 1.0 else 0.0 end) from fact_rcm_remits_SYNTHETIC where remit_seq = 1"),
    ("fact_rcm_remits_SYNTHETIC", "Clean Claim Rate (SYNTHETIC)",
     "VAR firsts = FILTER ( fact_rcm_remits_SYNTHETIC, fact_rcm_remits_SYNTHETIC[remit_seq] = 1 ) RETURN DIVIDE ( COUNTROWS ( FILTER ( firsts, "
     "fact_rcm_remits_SYNTHETIC[denied] = FALSE () && RELATED ( fact_rcm_claims_SYNTHETIC[scrubber_edit] ) = FALSE () ) ), COUNTROWS ( firsts ) )",
     "RCM (SYNTHETIC)", PCT, "SYNTHETIC demo: first-pass paid without scrubber edit / claims with a first remit.", "all",
     "select avg(case when not c.scrubber_edit and not r.denied then 1.0 else 0.0 end) from fact_rcm_claims_SYNTHETIC c "
     "join fact_rcm_remits_SYNTHETIC r on r.claim_id = c.claim_id and r.remit_seq = 1"),
    ("fact_rcm_claims_SYNTHETIC", "Net Collection Rate (SYNTHETIC)",
     "VAR mature = FILTER ( fact_rcm_claims_SYNTHETIC, fact_rcm_claims_SYNTHETIC[service_date] <= DATE ( 2026, 9, 30 ) - 90 ) RETURN DIVIDE ( "
     "SUMX ( mature, CALCULATE ( SUM ( fact_rcm_remits_SYNTHETIC[payer_paid] ) + SUM ( fact_rcm_remits_SYNTHETIC[patient_paid] ) ) ), "
     "SUMX ( mature, fact_rcm_claims_SYNTHETIC[expected_allowed] ) )",
     "RCM (SYNTHETIC)", PCT, "SYNTHETIC demo: payer + patient payments / expected allowed for claims >= 90 days old.", "all",
     "with mature as (select claim_id, expected_allowed from fact_rcm_claims_SYNTHETIC where service_date <= date '2026-09-30' - interval 90 day), "
     "cash as (select claim_id, sum(payer_paid + patient_paid) as collected from fact_rcm_remits_SYNTHETIC group by claim_id) "
     "select sum(coalesce(cash.collected, 0)) / sum(mature.expected_allowed) from mature left join cash using (claim_id)"),
    ("fact_rcm_claims_SYNTHETIC", "Days in AR (SYNTHETIC)",
     "VAR openAR = SUMX ( fact_rcm_claims_SYNTHETIC, VAR paid = CALCULATE ( COUNTROWS ( fact_rcm_remits_SYNTHETIC ), fact_rcm_remits_SYNTHETIC[denied] = FALSE () ) "
     "RETURN IF ( paid = 0, fact_rcm_claims_SYNTHETIC[expected_allowed], CALCULATE ( SUMX ( FILTER ( fact_rcm_remits_SYNTHETIC, "
     "fact_rcm_remits_SYNTHETIC[denied] = FALSE () ), fact_rcm_remits_SYNTHETIC[patient_resp] - fact_rcm_remits_SYNTHETIC[patient_paid] ) ) ) ) "
     "VAR daily = DIVIDE ( CALCULATE ( SUM ( fact_rcm_claims_SYNTHETIC[expected_allowed] ), fact_rcm_claims_SYNTHETIC[service_date] > DATE ( 2026, 9, 30 ) - 90 ), 90 ) "
     "RETURN DIVIDE ( openAR, daily )",
     "RCM (SYNTHETIC)", DEC, "SYNTHETIC demo: open AR / average daily net revenue, last 90 days.", "all",
     "with paid as (select claim_id, sum(patient_resp - patient_paid) as patient_open from fact_rcm_remits_SYNTHETIC where not denied group by claim_id), "
     "ar as (select sum(case when p.claim_id is null then c.expected_allowed else p.patient_open end) as open_ar from fact_rcm_claims_SYNTHETIC c "
     "left join paid p using (claim_id)), rev as (select sum(expected_allowed) / 90.0 as daily from fact_rcm_claims_SYNTHETIC "
     "where service_date > date '2026-09-30' - interval 90 day) select ar.open_ar / rev.daily from ar, rev"),
]


def slug(name: str) -> str:
    """'Median Lag Spread %' -> 'median_lag_spread_pct' (SQL twin file name and kpis.json key)."""
    s = name.replace("%", " pct").replace("(SYNTHETIC)", "SYNTHETIC")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
