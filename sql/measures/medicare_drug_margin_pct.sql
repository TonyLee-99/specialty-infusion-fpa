-- SQL twin of DAX measure [Medicare Drug Margin %] (table fact_margin_per_admin); runs on DuckDB over exports/*.csv
select sum(mix_share * drug_margin_medicare_ffs) / sum(mix_share * drug_collected_medicare) from fact_margin_per_admin
