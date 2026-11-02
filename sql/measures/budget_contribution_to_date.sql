-- SQL twin of DAX measure [Budget Contribution to Date] (table fact_actual_month_SYNTHETIC); context: site S1, months closed; DuckDB over exports/*.csv
select sum(contribution) from fact_plan_month where site_id = 'S1' and month_start <= (select max(month_start) from fact_actual_month_SYNTHETIC)
