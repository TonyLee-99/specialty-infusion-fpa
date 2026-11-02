-- Suppression-aware reconciliation: CMS drops provider rows with < 11 beneficiaries, so provider-level
-- sums can only fall short of the (unsuppressed) national totals, never exceed them.
with p as (
    select year, hcpcs, place_of_service, sum(services) as services, sum(allowed_amt) as allowed
    from {{ ref('fct_provider_drug_year') }} group by 1, 2, 3
)
select p.*, n.services as national_services
from p
join {{ ref('fct_national_drug_year') }} n using (year, hcpcs, place_of_service)
where p.services > n.services * 1.001 or p.allowed > n.allowed_amt * 1.001
