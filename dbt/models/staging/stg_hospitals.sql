-- Hospitals mapped to county by ZIP -> ZCTA; acute care only is used for the 'hospital-heavy' market flag.
select h."Facility ID" as ccn, h."Facility Name" as hospital_name, h."State" as state_abbr,
       lpad(h."ZIP Code", 5, '0') as zip5, h."Hospital Type" as hospital_type, z.county_fips
from {{ source('raw', 'hospitals') }} h
left join {{ ref('stg_zcta_county') }} z on z.zcta5 = lpad(h."ZIP Code", 5, '0')
