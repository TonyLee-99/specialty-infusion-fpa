"""DAX measures of the semantic model and the SQL twin that must reproduce each one's total value.

Each entry: (table, measure name, DAX, display folder, format string, description, SQL twin).
The SQL runs on DuckDB over exports/*.csv (one view per file, same name). `make kpis` writes the
SQL results to outputs/kpis.json; tests/test_tmdl.py checks names, files and values line up.
"""

from __future__ import annotations

import re

PCT, INT, CUR, DEC = "0.0%", "#,##0", "\\$#,##0", "#,##0.00"

MEASURES = [
    # ---------------- Pricing (ASP files) ----------------
    ("fact_asp_quarter", "Drugs Priced Latest Quarter",
     "VAR q = MAX ( fact_asp_quarter[quarter_start] ) RETURN CALCULATE ( DISTINCTCOUNT ( fact_asp_quarter[hcpcs] ), fact_asp_quarter[quarter_start] = q )",
     "Pricing", INT, "Catalog HCPCS with a published Medicare payment limit in the latest ASP quarter.",
     "select count(distinct hcpcs) from fact_asp_quarter where quarter_start = (select max(quarter_start) from fact_asp_quarter)"),
    ("fact_asp_quarter", "Median Lag Spread %",
     "MEDIAN ( fact_asp_quarter[lag_spread_pct] )",
     "Pricing", PCT, "Median of payment limit / current-quarter ASP - 1: what the 2-quarter ASP lag pays above today's price.",
     "select median(lag_spread_pct) from fact_asp_quarter where lag_spread_pct is not null"),
    ("fact_asp_quarter", "Underwater Quarter Share",
     "DIVIDE ( COUNTROWS ( FILTER ( fact_asp_quarter, fact_asp_quarter[lag_spread_pct] < 0 ) ), COUNTROWS ( FILTER ( fact_asp_quarter, NOT ISBLANK ( fact_asp_quarter[lag_spread_pct] ) ) ) )",
     "Pricing", PCT, "Share of drug-quarters where Medicare paid less than the current ASP (rising prices outran the lag).",
     "select avg(case when lag_spread_pct < 0 then 1.0 else 0.0 end) from fact_asp_quarter where lag_spread_pct is not null"),
    ("fact_asp_quarter", "IRA 8pct Add-on Codes Latest",
     "VAR q = MAX ( fact_asp_quarter[quarter_start] ) RETURN CALCULATE ( COUNTROWS ( fact_asp_quarter ), fact_asp_quarter[quarter_start] = q, fact_asp_quarter[flag_addon_8pct] = TRUE () )",
     "Pricing", INT, "Catalog biosimilars paid at ASP + 8% of reference ASP (IRA s.11403) in the latest quarter.",
     "select count(*) from fact_asp_quarter where flag_addon_8pct and quarter_start = (select max(quarter_start) from fact_asp_quarter)"),
    # ---------------- Utilization (national, Medicare FFS) ----------------
    ("fact_national_drug_year", "In-Office Administrations 2024",
     "CALCULATE ( SUM ( fact_national_drug_year[bene_day_services] ), fact_national_drug_year[year] = 2024, fact_national_drug_year[place_of_service] = \"O\", dim_drug[admin_family] IN { \"mab_infusion\", \"iv_infusion\", \"injection\" } )",
     "Utilization", INT, "National Medicare FFS beneficiary-days with an in-office administration of a catalog drug (chair + injection), 2024.",
     "select sum(n.bene_day_services) from fact_national_drug_year n join dim_drug d using (hcpcs) where n.year = 2024 and n.place_of_service = 'O' and d.admin_family in ('mab_infusion', 'iv_infusion', 'injection')"),
    ("fact_national_drug_year", "In-Office Drug Allowed 2024",
     "CALCULATE ( SUM ( fact_national_drug_year[allowed_amt] ), fact_national_drug_year[year] = 2024, fact_national_drug_year[place_of_service] = \"O\", NOT ISBLANK ( dim_drug[molecule] ) )",
     "Utilization", CUR, "National Medicare FFS allowed dollars for catalog drugs billed in an office, 2024.",
     "select sum(n.allowed_amt) from fact_national_drug_year n join dim_drug d using (hcpcs) where n.year = 2024 and n.place_of_service = 'O'"),
    ("fact_national_drug_year", "Infliximab Biosimilar Share 2024",
     "VAR t = CALCULATE ( SUM ( fact_national_drug_year[bene_day_services] ), fact_national_drug_year[year] = 2024, fact_national_drug_year[place_of_service] = \"O\", dim_drug[molecule] = \"infliximab\" ) RETURN DIVIDE ( CALCULATE ( SUM ( fact_national_drug_year[bene_day_services] ), fact_national_drug_year[year] = 2024, fact_national_drug_year[place_of_service] = \"O\", dim_drug[molecule] = \"infliximab\", dim_drug[is_biosimilar] = TRUE () ), t )",
     "Utilization", PCT, "Biosimilar share of in-office infliximab administrations, national Medicare FFS 2024.",
     "select sum(case when d.is_biosimilar then n.bene_day_services else 0 end) / sum(n.bene_day_services) from fact_national_drug_year n join dim_drug d using (hcpcs) where n.year = 2024 and n.place_of_service = 'O' and d.molecule = 'infliximab'"),
    # ---------------- Margin (per administration) ----------------
    ("fact_margin_per_admin", "Medicare Contribution per Admin",
     "DIVIDE ( SUMX ( fact_margin_per_admin, fact_margin_per_admin[mix_share] * fact_margin_per_admin[contribution_medicare_ffs] ), SUM ( fact_margin_per_admin[mix_share] ) )",
     "Margin", CUR, "Mix-weighted Medicare FFS contribution per chair infusion (drug margin + admin fee - chair cost), 2026Q4 prices.",
     "select sum(mix_share * contribution_medicare_ffs) / sum(mix_share) from fact_margin_per_admin"),
    ("fact_margin_per_admin", "Commercial Contribution per Admin",
     "DIVIDE ( SUMX ( fact_margin_per_admin, fact_margin_per_admin[mix_share] * fact_margin_per_admin[contribution_commercial] ), SUM ( fact_margin_per_admin[mix_share] ) )",
     "Margin", CUR, "Mix-weighted commercial contribution per chair infusion under the ASSUMED commercial contract (ASP + markup).",
     "select sum(mix_share * contribution_commercial) / sum(mix_share) from fact_margin_per_admin"),
    ("fact_margin_per_admin", "Medicare Drug Margin %",
     "DIVIDE ( SUMX ( fact_margin_per_admin, fact_margin_per_admin[mix_share] * fact_margin_per_admin[drug_margin_medicare_ffs] ), SUMX ( fact_margin_per_admin, fact_margin_per_admin[mix_share] * fact_margin_per_admin[drug_collected_medicare] ) )",
     "Margin", PCT, "Medicare FFS drug margin as % of collected drug revenue (ASP+6% after sequestration and coinsurance bad debt).",
     "select sum(mix_share * drug_margin_medicare_ffs) / sum(mix_share * drug_collected_medicare) from fact_margin_per_admin"),
    # ---------------- Scenarios (CY2027 plan) ----------------
    ("fact_scenarios", "Base Annual Contribution",
     "CALCULATE ( SUM ( fact_scenarios[value] ), fact_scenarios[scenario] = \"base\", fact_scenarios[metric] = \"contribution\" )",
     "Scenarios", CUR, "CY2027 base-case annual contribution of the illustrative 12-chair suite.",
     "select sum(value) from fact_scenarios where scenario = 'base' and metric = 'contribution'"),
    ("fact_scenarios", "Biosimilar Push Delta",
     "CALCULATE ( SUM ( fact_scenarios[value] ), fact_scenarios[scenario] = \"biosimilar_push\", fact_scenarios[metric] = \"contribution\" ) - [Base Annual Contribution]",
     "Scenarios", CUR, "Change in annual contribution if multi-source molecules move to the target biosimilar share.",
     "select sum(case when scenario = 'biosimilar_push' then value else -value end) from fact_scenarios where scenario in ('base', 'biosimilar_push') and metric = 'contribution'"),
    ("fact_scenarios", "Policy Shock Delta",
     "CALCULATE ( SUM ( fact_scenarios[value] ), fact_scenarios[scenario] = \"policy_shock\", fact_scenarios[metric] = \"contribution\" ) - [Base Annual Contribution]",
     "Scenarios", CUR, "Change in annual contribution under MFP for Orencia/Entyvio plus commercial white bagging (2028 run-rate).",
     "select sum(case when scenario = 'policy_shock' then value else -value end) from fact_scenarios where scenario in ('base', 'policy_shock') and metric = 'contribution'"),
    # ---------------- Benchmark ----------------
    ("fact_provider_scorecard", "Providers Scored",
     "COUNTROWS ( fact_provider_scorecard )",
     "Benchmark", INT, "Region rheumatology / neurology / GI / allergy-immunology clinicians with >= 11 Medicare beneficiaries, 2024.",
     "select count(*) from fact_provider_scorecard"),
    ("fact_provider_scorecard", "Median Allowed per Beneficiary",
     "MEDIAN ( fact_provider_scorecard[allowed_per_bene] )",
     "Benchmark", CUR, "Median Medicare allowed per beneficiary across scored providers (filter by specialty for peer view).",
     "select median(allowed_per_bene) from fact_provider_scorecard"),
    ("fact_provider_scorecard", "Providers Above Peer on Biosimilars",
     "COUNTROWS ( FILTER ( fact_provider_scorecard, fact_provider_scorecard[biosimilar_vs_peer] = \"above_peer\" ) )",
     "Benchmark", INT, "Providers whose 90% interval for shrunk biosimilar adoption sits above their specialty median.",
     "select count(*) from fact_provider_scorecard where biosimilar_vs_peer = 'above_peer'"),
    # ---------------- Market ----------------
    ("dim_market", "Eligible Markets",
     "COUNTROWS ( FILTER ( dim_market, dim_market[eligible] = TRUE () ) )",
     "Market", INT, "Markets (CBSA or stand-alone county) above the population screen.",
     "select count(*) from dim_market where eligible"),
    ("dim_market", "Top Market P(top 10)",
     "VAR best = MINX ( FILTER ( dim_market, dim_market[eligible] = TRUE () ), dim_market[rank] ) RETURN CALCULATE ( MAX ( dim_market[p_top10] ), dim_market[rank] = best )",
     "Market", PCT, "Share of 2,000 random weightings in which the #1 market stays in the top 10.",
     "select p_top10 from dim_market where rank = 1"),
    # ---------------- RCM (SYNTHETIC) ----------------
    ("fact_rcm_remits_SYNTHETIC", "Denial Rate (SYNTHETIC)",
     "CALCULATE ( DIVIDE ( COUNTROWS ( FILTER ( fact_rcm_remits_SYNTHETIC, fact_rcm_remits_SYNTHETIC[denied] = TRUE () ) ), COUNTROWS ( fact_rcm_remits_SYNTHETIC ) ), fact_rcm_remits_SYNTHETIC[remit_seq] = 1 )",
     "RCM (SYNTHETIC)", PCT, "SYNTHETIC demo: initial denials / first remits.",
     "select avg(case when denied then 1.0 else 0.0 end) from fact_rcm_remits_SYNTHETIC where remit_seq = 1"),
    ("fact_rcm_remits_SYNTHETIC", "Clean Claim Rate (SYNTHETIC)",
     "VAR firsts = FILTER ( fact_rcm_remits_SYNTHETIC, fact_rcm_remits_SYNTHETIC[remit_seq] = 1 ) RETURN DIVIDE ( COUNTROWS ( FILTER ( firsts, fact_rcm_remits_SYNTHETIC[denied] = FALSE () && RELATED ( fact_rcm_claims_SYNTHETIC[scrubber_edit] ) = FALSE () ) ), COUNTROWS ( firsts ) )",
     "RCM (SYNTHETIC)", PCT, "SYNTHETIC demo: first-pass paid without scrubber edit / claims with a first remit.",
     "select avg(case when not c.scrubber_edit and not r.denied then 1.0 else 0.0 end) from fact_rcm_claims_SYNTHETIC c join fact_rcm_remits_SYNTHETIC r on r.claim_id = c.claim_id and r.remit_seq = 1"),
    ("fact_rcm_claims_SYNTHETIC", "Net Collection Rate (SYNTHETIC)",
     "VAR mature = FILTER ( fact_rcm_claims_SYNTHETIC, fact_rcm_claims_SYNTHETIC[service_date] <= DATE ( 2026, 9, 30 ) - 90 ) RETURN DIVIDE ( SUMX ( mature, CALCULATE ( SUM ( fact_rcm_remits_SYNTHETIC[payer_paid] ) + SUM ( fact_rcm_remits_SYNTHETIC[patient_paid] ) ) ), SUMX ( mature, fact_rcm_claims_SYNTHETIC[expected_allowed] ) )",
     "RCM (SYNTHETIC)", PCT, "SYNTHETIC demo: payer + patient payments / expected allowed for claims >= 90 days old.",
     "with mature as (select claim_id, expected_allowed from fact_rcm_claims_SYNTHETIC where service_date <= date '2026-09-30' - interval 90 day), cash as (select claim_id, sum(payer_paid + patient_paid) as collected from fact_rcm_remits_SYNTHETIC group by claim_id) select sum(coalesce(cash.collected, 0)) / sum(mature.expected_allowed) from mature left join cash using (claim_id)"),
    ("fact_rcm_claims_SYNTHETIC", "Days in AR (SYNTHETIC)",
     "VAR openAR = SUMX ( fact_rcm_claims_SYNTHETIC, VAR paid = CALCULATE ( COUNTROWS ( fact_rcm_remits_SYNTHETIC ), fact_rcm_remits_SYNTHETIC[denied] = FALSE () ) RETURN IF ( paid = 0, fact_rcm_claims_SYNTHETIC[expected_allowed], CALCULATE ( SUMX ( FILTER ( fact_rcm_remits_SYNTHETIC, fact_rcm_remits_SYNTHETIC[denied] = FALSE () ), fact_rcm_remits_SYNTHETIC[patient_resp] - fact_rcm_remits_SYNTHETIC[patient_paid] ) ) ) ) VAR daily = DIVIDE ( CALCULATE ( SUM ( fact_rcm_claims_SYNTHETIC[expected_allowed] ), fact_rcm_claims_SYNTHETIC[service_date] > DATE ( 2026, 9, 30 ) - 90 ), 90 ) RETURN DIVIDE ( openAR, daily )",
     "RCM (SYNTHETIC)", DEC, "SYNTHETIC demo: open AR (unpaid claims + unpaid patient balances) / average daily net revenue, last 90 days.",
     "with paid as (select claim_id, sum(patient_resp - patient_paid) as patient_open from fact_rcm_remits_SYNTHETIC where not denied group by claim_id), ar as (select sum(case when p.claim_id is null then c.expected_allowed else p.patient_open end) as open_ar from fact_rcm_claims_SYNTHETIC c left join paid p using (claim_id)), rev as (select sum(expected_allowed) / 90.0 as daily from fact_rcm_claims_SYNTHETIC where service_date > date '2026-09-30' - interval 90 day) select ar.open_ar / rev.daily from ar, rev"),
]


def slug(name: str) -> str:
    """'Median Lag Spread %' -> 'median_lag_spread_pct' (SQL twin file name and kpis.json key)."""
    s = name.replace("%", " pct").replace("(SYNTHETIC)", "SYNTHETIC")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
