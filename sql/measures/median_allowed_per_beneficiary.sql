-- SQL twin of DAX measure [Median Allowed per Beneficiary] (table fact_provider_scorecard); context: provider_type = Rheumatology; DuckDB over exports/*.csv
select median(allowed_per_bene) from fact_provider_scorecard where provider_type = 'Rheumatology'
