-- County dimension for the 7 region states: population, 65+, arthritis prevalence, Medicare FFS/MA.
select
    p.county_fips, p.state_name, p.county_name, r.state_abbr,
    p.population, p.pop_65plus, p.pop_18plus,
    pl.arthritis_prev, pl.arthritis_prev_95ci,
    e.medicare_benes, e.original_medicare_benes, e.ma_benes, e.ffs_share, e.year as enrollment_year
from {{ ref('stg_census_pep_county') }} p
join {{ ref('region_states') }} r on r.state_fips = left(p.county_fips, 2)
left join {{ ref('stg_places_county') }} pl using (county_fips)
left join {{ ref('stg_medicare_enrollment_county') }} e using (county_fips)
where right(p.county_fips, 3) <> '000'
