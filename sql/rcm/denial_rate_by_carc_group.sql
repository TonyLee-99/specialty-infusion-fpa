-- SYNTHETIC demo. Initial denials by CARC group as a share of all first remits.
select carc_group as key, count(*) * 1.0 / (select count(*) from remits where remit_seq = 1) as value
from remits
where remit_seq = 1 and denied
group by carc_group
order by value desc
