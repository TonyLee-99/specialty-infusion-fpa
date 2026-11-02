-- SQL twin of DAX measure [Budget Operating Margin] (table fact_plan_month); context: site S1, full year; DuckDB over exports/*.csv
select (select sum(contribution) from fact_plan_month where site_id = 'S1') - (select sum(fixed_total) from fact_fixed_month where site_id = 'S1')
