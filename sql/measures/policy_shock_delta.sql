-- SQL twin of DAX measure [Policy Shock Delta] (table fact_scenarios); runs on DuckDB over exports/*.csv
select sum(case when scenario = 'policy_shock' then value else -value end) from fact_scenarios where scenario in ('base', 'policy_shock') and metric = 'contribution'
