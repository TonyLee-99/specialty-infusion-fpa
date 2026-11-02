-- SYNTHETIC demo. Days in AR = open AR at the as-of date / average daily net (expected allowed) revenue
-- over the last 90 days. Open AR = expected allowed on claims never paid + unpaid patient balances.
with paid as (
    select claim_id, sum(payer_paid) as payer_paid, sum(patient_resp - patient_paid) as patient_open
    from remits where not denied group by claim_id
),
ar as (
    select sum(case when p.claim_id is null then c.expected_allowed else p.patient_open end) as open_ar
    from claims c left join paid p using (claim_id)
),
rev as (
    select sum(expected_allowed) / 90.0 as daily
    from claims where service_date > date '2026-09-30' - interval 90 day
)
select ar.open_ar / rev.daily as value from ar, rev
