-- Wide 2020-2024 file -> long. All settings (office + hospital outpatient). Overall rows only.
with base as (
    select * from {{ source('raw', 'partb_spending_annual') }}
)
{% for y in [2020, 2021, 2022, 2023, 2024] %}
select
    HCPCS_Cd as hcpcs, Brnd_Name as brand_name, Gnrc_Name as generic_name, {{ y }} as year,
    try_cast(nullif(Tot_Spndng_{{ y }}, '') as double)   as total_spending,
    try_cast(nullif(Tot_Dsg_Unts_{{ y }}, '') as double) as total_units,
    try_cast(nullif(Tot_Clms_{{ y }}, '') as double)     as total_claims,
    try_cast(nullif(Tot_Benes_{{ y }}, '') as double)    as total_benes
from base
{% if not loop.last %}union all{% endif %}
{% endfor %}
