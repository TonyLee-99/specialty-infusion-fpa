select
    lpad(STATE, 2, '0') || lpad(COUNTY, 3, '0') as county_fips,
    STNAME as state_name, CTYNAME as county_name,
    cast(POPESTIMATE as double) as population,
    cast(AGE65PLUS_TOT as double) as pop_65plus,
    cast(AGE18PLUS_TOT as double) as pop_18plus
from {{ source('raw', 'census_pep_county') }}
