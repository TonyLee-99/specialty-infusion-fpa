-- SQL twin of DAX measure [In-Office Drug Allowed 2024] (table fact_national_drug_year); runs on DuckDB over exports/*.csv
select sum(n.allowed_amt) from fact_national_drug_year n join dim_drug d using (hcpcs) where n.year = 2024 and n.place_of_service = 'O'
