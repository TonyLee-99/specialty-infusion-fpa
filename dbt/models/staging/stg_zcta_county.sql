-- A ZCTA can straddle counties: assign each to the county holding the largest land area share.
select
    GEOID_ZCTA5_20 as zcta5,
    GEOID_COUNTY_20 as county_fips
from {{ source('raw', 'zcta_county') }}
where GEOID_COUNTY_20 is not null and GEOID_COUNTY_20 <> ''
qualify row_number() over (partition by GEOID_ZCTA5_20 order by cast(AREALAND_PART as bigint) desc) = 1
