-- SQL twin of DAX measure [Budget Administrations] (table fact_plan_month); context: site S1, full year; DuckDB over exports/*.csv
select sum(admins) from fact_plan_month where site_id = 'S1'
