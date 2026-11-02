-- Business rule (IRA s.11403): a biosimilar gets the 8% add-on only if its ASP <= the reference ASP.
-- Checks the published flag against our implied ASPs (0.5% tolerance for rounding of published PLs).
select hcpcs, payment_quarter, implied_asp, ref_asp
from {{ ref('int_asp_implied') }}
where flag_addon_8pct and implied_asp is not null and ref_asp is not null
  and implied_asp > ref_asp * 1.005
