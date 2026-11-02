-- Price fact: published payment limit, implied ASPs and the 2-quarter lag spread (ADR 0003).
--   asp_basis    = ASP behind this quarter's PL (sales of t-2)
--   asp_current  = ASP of sales in quarter t itself, read from the PL published two quarters later
--   lag_spread   = PL(t) - asp_current(t): what Medicare pays above (or below) the current market price
with x as (
    select *,
        lead(implied_asp, 2) over (partition by hcpcs order by quarter_start) as asp_current,
        lead(quarter_start, 2) over (partition by hcpcs order by quarter_start) as next2_start
    from {{ ref('int_asp_implied') }}
)
select
    payment_quarter, quarter_start, hcpcs, molecule, product_type,
    payment_limit, addon_pct, ref_asp, implied_asp as asp_basis,
    -- only trust lead() when the row two steps ahead is exactly two quarters ahead
    case when next2_start = quarter_start + interval 6 month then asp_current end as asp_current,
    case when next2_start = quarter_start + interval 6 month
         then payment_limit - asp_current end as lag_spread,
    case when next2_start = quarter_start + interval 6 month and asp_current > 0
         then payment_limit / asp_current - 1 end as lag_spread_pct,
    flag_addon_8pct, flag_lesser_of, flag_amp_based, coinsurance_pct, notes
from x
