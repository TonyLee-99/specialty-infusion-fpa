-- SYNTHETIC demo. Clean-claim rate = claims accepted and paid on first pass (no scrubber edit, first
-- remit not denied) / claims with a first remit.
select avg(case when not c.scrubber_edit and not r.denied then 1.0 else 0.0 end) as value
from claims c
join remits r on r.claim_id = c.claim_id and r.remit_seq = 1
