-- SQL twin of DAX measure [Drugs Priced Latest Quarter] (table fact_asp_quarter); runs on DuckDB over exports/*.csv
select count(distinct hcpcs) from fact_asp_quarter where quarter_start = (select max(quarter_start) from fact_asp_quarter)
