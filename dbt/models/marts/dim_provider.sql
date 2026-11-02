-- Provider dimension (no names). Totals from the 2024 by-Provider file where available.
select
    c.npi, c.provider_type, c.state_abbr, c.zip5, c.county_fips,
    p.entity_code, p.benes as total_benes_2024, p.services as total_services_2024, p.allowed_amt as total_allowed_2024,
    p.drug_allowed_amt as drug_allowed_2024, p.medical_allowed_amt as medical_allowed_2024,
    p.avg_risk_score as avg_risk_score_2024,
    c.state_abbr in (select state_abbr from {{ ref('region_states') }}) as in_region
from {{ ref('int_provider_county') }} c
left join {{ ref('stg_provider') }} p on p.npi = c.npi and p.year = 2024
