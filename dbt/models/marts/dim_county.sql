-- County dimension for the 7 region states: population, 65+, arthritis prevalence, Medicare FFS/MA.
select
    p.county_fips, p.state_name, p.county_name, r.state_abbr,
    p.population, p.pop_65plus, p.pop_18plus,
    pl.arthritis_prev, pl.arthritis_prev_95ci,
    e.medicare_benes, e.original_medicare_benes, e.ma_benes, e.ffs_share, e.year as enrollment_year,
    gz.lat, gz.lon, gz.land_sqmi,
    -- market grain: the metro/micro area, or the county itself when it sits outside any CBSA
    coalesce(cb.cbsa_code, 'C' || p.county_fips) as market_id,
    coalesce(cb.cbsa_title, p.county_name || ', ' || r.state_abbr) as market_name,
    coalesce(cb.cbsa_type, 'Non-CBSA county') as market_type,
    coalesce(cbn.n_counties_total, 1) as market_counties_total
from {{ ref('stg_census_pep_county') }} p
join {{ ref('region_states') }} r on r.state_fips = left(p.county_fips, 2)
left join {{ ref('stg_places_county') }} pl using (county_fips)
left join {{ ref('stg_medicare_enrollment_county') }} e using (county_fips)
left join {{ ref('stg_county_gazetteer') }} gz using (county_fips)
left join {{ source('raw', 'cbsa_county') }} cb using (county_fips)
left join (select cbsa_code, count(*) as n_counties_total from {{ source('raw', 'cbsa_county') }} group by 1) cbn
    on cbn.cbsa_code = cb.cbsa_code
where right(p.county_fips, 3) <> '000'
