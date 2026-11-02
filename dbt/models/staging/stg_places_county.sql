-- Newest PLACES release with a non-null arthritis estimate per county (2025; 2024 for KY and PA).
select
    countyfips as county_fips, stateabbr as state_abbr, countyname as county_name,
    cast(totalpopulation as double) as places_population,
    cast(totalpop18plus as double) as places_pop_18plus,
    cast(arthritis_crudeprev as double) / 100 as arthritis_prev,
    arthritis_crude95ci as arthritis_prev_95ci,
    places_release
from {{ source('raw', 'places_county') }}
where arthritis_crudeprev is not null and arthritis_crudeprev not in ('', 'None', 'nan')
qualify row_number() over (partition by countyfips order by places_release desc) = 1
