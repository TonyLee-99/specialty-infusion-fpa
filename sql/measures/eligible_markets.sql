-- SQL twin of DAX measure [Eligible Markets] (table dim_market); runs on DuckDB over exports/*.csv
select count(*) from dim_market where eligible
