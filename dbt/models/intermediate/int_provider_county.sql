-- Provider zip5 -> county FIPS via the ZCTA relationship file (ZIP != ZCTA caveat, ADR 0002).
with npis as (
    select npi, zip5, state_abbr, provider_type, year from {{ ref('stg_provider') }}
    union all
    select npi, zip5, state_abbr, provider_type, year from {{ ref('stg_provider_service') }}
)
select npi, zip5, state_abbr, provider_type, z.county_fips
from npis
left join {{ ref('stg_zcta_county') }} z on z.zcta5 = npis.zip5
qualify row_number() over (partition by npi order by year desc, provider_type) = 1
