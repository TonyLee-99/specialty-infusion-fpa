-- SQL twin of DAX measure [Budget Fixed Costs] (table fact_fixed_month); context: site S1, full year; DuckDB over exports/*.csv
select sum(fixed_total) from fact_fixed_month where site_id = 'S1'
