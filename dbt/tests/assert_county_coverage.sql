-- Every county in scope has population, arthritis prevalence and a location; region counties also have
-- Medicare enrollment (enrollment was pulled for the 7 region states only).
select county_fips from {{ ref('dim_county') }}
where population is null or arthritis_prev is null or lat is null
   or (in_region and medicare_benes is null)
