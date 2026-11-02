-- Reconciliation (payment = allowed): national in-office allowed per billed unit should not exceed the
-- year's highest quarterly payment limit (allowed = lesser of charge or PL). Allowed BELOW PL is
-- measured and reported by `make dq` (outputs/dq_report.json) rather than failed here.
with pl as (
    select hcpcs, year(quarter_start) as year, max(payment_limit) as max_pl
    from {{ ref('fct_asp_quarter') }} group by 1, 2
)
select n.hcpcs, n.year, n.avg_allowed, pl.max_pl
from {{ ref('fct_national_drug_year') }} n
join pl using (hcpcs, year)
where n.place_of_service = 'O' and n.services > 0 and n.avg_allowed > pl.max_pl * 1.02
