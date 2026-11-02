-- SQL twin of DAX measure [Underwater Quarter Share] (table fact_asp_quarter); runs on DuckDB over exports/*.csv
select avg(case when lag_spread_pct < 0 then 1.0 else 0.0 end) from fact_asp_quarter where lag_spread_pct is not null
