-- SQL twin of DAX measure [Actual Contribution (SYNTHETIC)] (table fact_actual_month_SYNTHETIC); context: site S1, months closed; DuckDB over exports/*.csv
select sum(contribution) from fact_actual_month_SYNTHETIC where site_id = 'S1'
