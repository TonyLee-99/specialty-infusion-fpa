-- SYNTHETIC demo. Initial denial rate = first remits that are denials / first remits.
select avg(case when denied then 1.0 else 0.0 end) as value
from remits
where remit_seq = 1
