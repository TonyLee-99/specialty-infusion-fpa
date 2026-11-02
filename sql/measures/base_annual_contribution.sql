-- SQL twin of DAX measure [Base Annual Contribution] (table fact_scenarios); runs on DuckDB over exports/*.csv
select sum(value) from fact_scenarios where scenario = 'base' and metric = 'contribution'
