-- One row per HCPCS x payment quarter. PL for quarter t is built from ASP data of quarter t-2.
select
    quarter                                             as payment_quarter,
    {{ quarter_start('quarter') }}                      as quarter_start,
    hcpcs,
    short_desc,
    dosage,
    try_cast(replace(payment_limit, ',', '') as double) as payment_limit,
    try_cast(nullif(coinsurance_pct, '') as double)     as coinsurance_pct,
    notes,
    nullif(asp_basis_quarter, '')                       as asp_basis_quarter,
    notes ilike '%8% of reference%'                     as flag_addon_8pct,
    notes ilike '%lesser of%'                           as flag_lesser_of,
    notes ilike '%AMP-based%'                           as flag_amp_based,
    notes ilike '%inflation-adjusted coinsurance%'      as flag_inflation_coins
from {{ source('raw', 'asp_payment_limits') }}
where try_cast(replace(payment_limit, ',', '') as double) > 0
-- A handful of files list a code twice (restated rows); keep the row with the HIGHEST payment limit
-- (deterministic; the duplicates seen differ by rounding only).
qualify row_number() over (partition by quarter, hcpcs order by try_cast(replace(payment_limit, ',', '') as double) desc) = 1
