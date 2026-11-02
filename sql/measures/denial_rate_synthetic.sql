-- SQL twin of DAX measure [Denial Rate (SYNTHETIC)] (table fact_rcm_remits_SYNTHETIC); context: all; DuckDB over exports/*.csv
select avg(case when denied then 1.0 else 0.0 end) from fact_rcm_remits_SYNTHETIC where remit_seq = 1
