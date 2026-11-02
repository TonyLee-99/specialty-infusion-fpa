-- Every county in the 7 region states has population, arthritis prevalence and Medicare enrollment.
select county_fips from {{ ref('dim_county') }}
where population is null or arthritis_prev is null or medicare_benes is null or lat is null
