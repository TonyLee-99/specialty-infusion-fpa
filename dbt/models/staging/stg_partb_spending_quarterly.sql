-- Latest quarterly release: '2025 (Q1-Q4)' and '2026 (Q1)' rows. Used as a 2025 out-of-sample check.
select
    HCPCS_Cd as hcpcs, Brnd_Name as brand_name, Gnrc_Name as generic_name,
    Year as period_label,
    cast(left(Year, 4) as int) as year,
    Year like '%Q1-Q4%' as is_full_year,
    try_cast(Tot_Spndng as double) as total_spending,
    try_cast(Tot_Clms as double) as total_claims,
    try_cast(Tot_Benes as double) as total_benes
from {{ source('raw', 'partb_spending_quarterly') }}
