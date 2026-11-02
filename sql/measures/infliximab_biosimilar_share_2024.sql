-- SQL twin of DAX measure [Infliximab Biosimilar Share 2024] (table fact_national_drug_year); runs on DuckDB over exports/*.csv
select sum(case when d.is_biosimilar then n.bene_day_services else 0 end) / sum(n.bene_day_services) from fact_national_drug_year n join dim_drug d using (hcpcs) where n.year = 2024 and n.place_of_service = 'O' and d.molecule = 'infliximab'
