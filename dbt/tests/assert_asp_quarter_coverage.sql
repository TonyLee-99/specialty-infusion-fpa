-- Business rule: 40 consecutive payment quarters 2017Q1-2026Q4, each with an ASP basis two quarters back.
with q as (
    select payment_quarter, quarter_start, max(asp_basis_quarter) as basis
    from {{ ref('stg_asp_payment_limits') }} group by 1, 2
)
select 'coverage' as problem, count(*) as n from q having count(*) <> 40
union all
select 'basis lag != 2 quarters', count(*) from q
where basis is not null
  and {{ quarter_start('basis') }} <> quarter_start - interval 6 month
having count(*) > 0
