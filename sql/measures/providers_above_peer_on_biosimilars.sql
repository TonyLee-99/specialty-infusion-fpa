-- SQL twin of DAX measure [Providers Above Peer on Biosimilars] (table fact_provider_scorecard); runs on DuckDB over exports/*.csv
select count(*) from fact_provider_scorecard where biosimilar_vs_peer = 'above_peer'
