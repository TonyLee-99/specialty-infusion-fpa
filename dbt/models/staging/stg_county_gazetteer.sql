select GEOID as county_fips, USPS as state_abbr, NAME as county_name,
       cast(INTPTLAT as double) as lat, cast(INTPTLONG as double) as lon,
       cast(ALAND_SQMI as double) as land_sqmi
from {{ source('raw', 'county_gazetteer') }}
