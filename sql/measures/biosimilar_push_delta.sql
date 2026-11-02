-- SQL twin of DAX measure [Biosimilar Push Delta] (table fact_scenarios); runs on DuckDB over exports/*.csv
select sum(case when scenario = 'biosimilar_push' then value else -value end) from fact_scenarios where scenario in ('base', 'biosimilar_push') and metric = 'contribution'
