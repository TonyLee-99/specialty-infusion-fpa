select g.geo_desc as state_name, s.state_abbr, g.hcpcs, g.place_of_service, g.providers, g.benes,
       g.services, g.bene_day_services, g.allowed_amt
from {{ ref('stg_geo_service') }} g
join {{ ref('region_states') }} s on s.state_name = g.geo_desc
where g.geo_level = 'State' and g.year = 2024
  and (g.hcpcs in (select hcpcs from {{ ref('drug_catalog') }})
       or g.hcpcs in (select hcpcs from {{ ref('admin_codes') }}))
