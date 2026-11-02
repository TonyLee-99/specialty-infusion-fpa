-- SYNTHETIC demo. Net collection rate = (payer + patient payments) / expected allowed (charges net of
-- contractual adjustments), for claims old enough to have resolved (service date >= 90 days before as-of).
with mature as (
    select claim_id, expected_allowed from claims where service_date <= date '2026-09-30' - interval 90 day
),
cash as (
    select claim_id, sum(payer_paid + patient_paid) as collected from remits group by claim_id
)
select sum(coalesce(cash.collected, 0)) / sum(mature.expected_allowed) as value
from mature left join cash using (claim_id)
