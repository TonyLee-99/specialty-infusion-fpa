-- County dimension: the 7 region states, plus out-of-region counties of CBSAs that cross into the region
-- (St. Louis MO-IL, Philadelphia PA-NJ-DE-MD, ...), so cross-state metros are scored whole.
with cb as (select * from {{ source('raw', 'cbsa_county') }}),
region_cbsa as (
    select distinct cbsa_code from cb
    where left(county_fips, 2) in (select state_fips from {{ ref('region_states') }})
),
scope as (
    select p.county_fips, left(p.county_fips, 2) in (select state_fips from {{ ref('region_states') }}) as in_region
    from {{ ref('stg_census_pep_county') }} p
    left join cb using (county_fips)
    where right(p.county_fips, 3) <> '000'
      and (left(p.county_fips, 2) in (select state_fips from {{ ref('region_states') }})
           or cb.cbsa_code in (select cbsa_code from region_cbsa))
),
hosp as (
    select county_fips, count(*) filter (where hospital_type = 'Acute Care Hospitals') as acute_hospitals
    from {{ ref('stg_hospitals') }} group by 1
)
select
    p.county_fips, p.state_name, p.county_name,
    coalesce(r.state_abbr, x.state_abbr) as state_abbr, s.in_region,
    p.population, p.pop_65plus, p.pop_18plus,
    pl.arthritis_prev, pl.arthritis_prev_95ci,
    e.medicare_benes, e.original_medicare_benes, e.ma_benes, e.ffs_share, e.year as enrollment_year,
    gz.lat, gz.lon, gz.land_sqmi,
    coalesce(h.acute_hospitals, 0) as acute_hospitals,
    -- market grain: the metro/micro area, or the county itself when it sits outside any CBSA
    coalesce(cb.cbsa_code, 'C' || p.county_fips) as market_id,
    coalesce(cb.cbsa_title, p.county_name || ', ' || coalesce(r.state_abbr, x.state_abbr)) as market_name,
    coalesce(cb.cbsa_type, 'Non-CBSA county') as market_type,
    coalesce(cbn.n_counties_total, 1) as market_counties_total
from {{ ref('stg_census_pep_county') }} p
join scope s using (county_fips)
left join {{ ref('region_states') }} r on r.state_fips = left(p.county_fips, 2)
left join {{ ref('market_extra_states') }} x on x.state_fips = left(p.county_fips, 2)
left join {{ ref('stg_places_county') }} pl using (county_fips)
left join {{ ref('stg_medicare_enrollment_county') }} e using (county_fips)
left join {{ ref('stg_county_gazetteer') }} gz using (county_fips)
left join cb using (county_fips)
left join (select cbsa_code, count(*) as n_counties_total from cb group by 1) cbn on cbn.cbsa_code = cb.cbsa_code
left join hosp h using (county_fips)
