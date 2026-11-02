-- National Medicare FFS totals per catalog/admin HCPCS x place of service x year (2013-2024).
select g.year, g.hcpcs, g.place_of_service, g.providers, g.benes, g.services,
       g.bene_day_services, g.avg_allowed, g.allowed_amt, g.payment_amt
from {{ ref('stg_geo_service') }} g
where g.geo_level = 'National'
  and (g.hcpcs in (select hcpcs from {{ ref('drug_catalog') }})
       or g.hcpcs in (select hcpcs from {{ ref('admin_codes') }}))
