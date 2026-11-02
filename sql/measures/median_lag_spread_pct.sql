-- SQL twin of DAX measure [Median Lag Spread %] (table fact_asp_quarter); context: all drugs, all quarters; DuckDB over exports/*.csv
select median(lag_spread_pct) from fact_asp_quarter where lag_spread_pct is not null
