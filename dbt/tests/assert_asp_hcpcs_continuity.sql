-- Business rule: once a catalog HCPCS appears in the ASP files it is present every quarter until it is
-- retired; a retired code must hand over to its successor in the very next quarter (hcpcs_successors).
with a as (
    select hcpcs, quarter_start
    from {{ ref('stg_asp_payment_limits') }}
    where hcpcs in (select hcpcs from {{ ref('drug_catalog') }})
),
spans as (
    select hcpcs, min(quarter_start) as first_q, max(quarter_start) as last_q, count(*) as n
    from a group by hcpcs
),
gaps as (
    select hcpcs, 'gap inside span' as problem from spans
    where n <> date_diff('month', first_q, last_q) / 3 + 1
),
latest as (select max(quarter_start) as q from a),
retired_without_successor as (
    select s.hcpcs, 'retired without successor' as problem
    from spans s, latest
    where s.last_q < latest.q
      and s.hcpcs not in (select old_hcpcs from {{ ref('hcpcs_successors') }})
),
bad_handover as (
    select o.hcpcs, 'successor does not start next quarter' as problem
    from {{ ref('hcpcs_successors') }} h
    join spans o on o.hcpcs = h.old_hcpcs
    join spans n on n.hcpcs = h.new_hcpcs
    where n.first_q <> o.last_q + interval 3 month
)
select * from gaps union all select * from retired_without_successor union all select * from bad_handover
