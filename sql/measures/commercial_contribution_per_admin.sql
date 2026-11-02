-- SQL twin of DAX measure [Commercial Contribution per Admin] (table fact_margin_per_admin); runs on DuckDB over exports/*.csv
select sum(mix_share * contribution_commercial) / sum(mix_share) from fact_margin_per_admin
