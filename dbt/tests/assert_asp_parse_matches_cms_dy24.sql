-- External reconciliation: the mean of our four parsed 2024 quarterly payment limits must equal the
-- 'Avg_DY24_ASP_Price' CMS publishes in the Part B Spending by Drug file (independent CMS product),
-- for every catalog code present in both (tolerance 0.1%).
with ours as (
    select hcpcs, avg(payment_limit) as pl_2024
    from {{ ref('stg_asp_payment_limits') }}
    where payment_quarter like '2024Q%'
    group by hcpcs having count(*) = 4
),
cms as (
    select HCPCS_Cd as hcpcs, try_cast(nullif(Avg_DY24_ASP_Price, '') as double) as cms_avg
    from {{ source('raw', 'partb_spending_annual') }}
)
select o.hcpcs, o.pl_2024, c.cms_avg
from ours o
join cms c using (hcpcs)
join {{ ref('drug_catalog') }} d using (hcpcs)
where c.cms_avg > 0 and abs(o.pl_2024 / c.cms_avg - 1) > 0.001
