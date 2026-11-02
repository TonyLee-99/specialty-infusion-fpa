-- All-settings Medicare Part B spend per catalog HCPCS: 2020-2024 annual + 2025 from the quarterly file.
select hcpcs, year, total_spending, total_claims, total_benes, total_units, 'annual_file' as source
from {{ ref('stg_partb_spending_annual') }}
where hcpcs in (select hcpcs from {{ ref('drug_catalog') }}) and total_spending is not null
union all
select hcpcs, year, total_spending, total_claims, total_benes, null as total_units, 'quarterly_file_2025' as source
from {{ ref('stg_partb_spending_quarterly') }}
where is_full_year and hcpcs in (select hcpcs from {{ ref('drug_catalog') }})
