-- SQL twin of DAX measure [Top Market P(top 10)] (table dim_market); runs on DuckDB over exports/*.csv
select p_top10 from dim_market where rank = 1
