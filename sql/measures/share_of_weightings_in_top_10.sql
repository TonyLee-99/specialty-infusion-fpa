-- SQL twin of DAX measure [Share of Weightings in Top 10] (table dim_market); context: market = Canton-Massillon, OH; DuckDB over exports/*.csv
select share_of_weightings_in_top10 from dim_market where market_name = 'Canton-Massillon, OH'
