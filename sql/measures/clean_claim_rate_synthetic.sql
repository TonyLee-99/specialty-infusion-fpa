-- SQL twin of DAX measure [Clean Claim Rate (SYNTHETIC)] (table fact_rcm_remits_SYNTHETIC); runs on DuckDB over exports/*.csv
select avg(case when not c.scrubber_edit and not r.denied then 1.0 else 0.0 end) from fact_rcm_claims_SYNTHETIC c join fact_rcm_remits_SYNTHETIC r on r.claim_id = c.claim_id and r.remit_seq = 1
