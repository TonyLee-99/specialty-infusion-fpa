-- SQL twin of DAX measure [Providers Below State on Biosimilars] (table fact_provider_scorecard); context: all; DuckDB over exports/*.csv
select count(*) from fact_provider_scorecard where biosimilar_vs_state = 'below_state'
