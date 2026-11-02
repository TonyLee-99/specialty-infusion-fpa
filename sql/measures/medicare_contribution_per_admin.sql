-- SQL twin of DAX measure [Medicare Contribution per Admin] (table fact_margin_per_admin); runs on DuckDB over exports/*.csv
select sum(mix_share * contribution_medicare_ffs) / sum(mix_share) from fact_margin_per_admin
