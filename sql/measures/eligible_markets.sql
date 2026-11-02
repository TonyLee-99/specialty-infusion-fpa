-- SQL twin of DAX measure [Eligible Markets] (table dim_market); context: all; DuckDB over exports/*.csv
select count(*) from dim_market where eligible
