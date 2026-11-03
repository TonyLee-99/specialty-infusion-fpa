-- Provider ZIP -> county. Step 1: Census ZCTA relationship file (ZIP != ZCTA caveat, ADR 0002).
-- Step 2: unique / campus ZIPs have no ZCTA (e.g. 44195, the Cleveland Clinic campus,
-- 238 region specialists). They take the county that most providers in the same USPS city + state map to
-- through step 1. county_method records which step placed the provider; dq.py fails if too many stay unmapped.
with npis as (
    select npi, zip5, city, state_abbr, provider_type, year from {{ ref('stg_provider') }}
    union all
    select npi, zip5, city, state_abbr, provider_type, year from {{ ref('stg_provider_service') }}
),
latest as (
    select * from npis
    qualify row_number() over (partition by npi order by year desc, provider_type) = 1
),
zcta as (
    select l.*, z.county_fips as zcta_county
    from latest l left join {{ ref('stg_zcta_county') }} z on z.zcta5 = l.zip5
),
city_county as (
    select state_abbr, city, zcta_county as county_fips
    from zcta where zcta_county is not null
    group by 1, 2, 3
    qualify row_number() over (partition by state_abbr, city order by count(*) desc, zcta_county) = 1
)
select z.npi, z.zip5, z.state_abbr, z.provider_type,
       coalesce(z.zcta_county, c.county_fips) as county_fips,
       case when z.zcta_county is not null then 'zcta'
            when c.county_fips is not null then 'usps_city_state'
            else 'unmapped' end as county_method
from zcta z
left join city_county c using (state_abbr, city)
