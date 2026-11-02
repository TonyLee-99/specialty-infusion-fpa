-- SQL twin of DAX measure [Providers Scored] (table fact_provider_scorecard); runs on DuckDB over exports/*.csv
select count(*) from fact_provider_scorecard
