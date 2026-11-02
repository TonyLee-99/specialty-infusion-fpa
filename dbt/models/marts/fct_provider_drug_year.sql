-- Provider x HCPCS x place of service x year, catalog drugs and admin codes only.
select
    s.year, s.npi, s.hcpcs, s.place_of_service,
    coalesce(d.molecule, 'admin') as molecule,
    case when d.hcpcs is not null then 'drug' else 'admin' end as hcpcs_role,
    s.benes, s.services, s.bene_day_services, s.avg_allowed, s.allowed_amt, s.payment_amt
from {{ ref('stg_provider_service') }} s
left join {{ ref('dim_drug') }} d on d.hcpcs = s.hcpcs
left join {{ ref('admin_codes') }} a on a.hcpcs = s.hcpcs
where d.hcpcs is not null or a.hcpcs is not null
