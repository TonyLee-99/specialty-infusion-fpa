-- SQL twin of DAX measure [Median Allowed per Beneficiary] (table fact_provider_scorecard); runs on DuckDB over exports/*.csv
select median(allowed_per_bene) from fact_provider_scorecard
