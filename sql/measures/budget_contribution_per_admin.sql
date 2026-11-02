-- SQL twin of DAX measure [Budget Contribution per Admin] (table fact_plan_month); context: payer = commercial, site S1; DuckDB over exports/*.csv
select sum(contribution) / sum(admins) from fact_plan_month where site_id = 'S1' and payer = 'commercial'
