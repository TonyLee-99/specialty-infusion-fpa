-- Business rule: Medicare payment never exceeds the allowed amount (row level), and across all catalog
-- drugs nationally the payment/allowed ratio sits just under 0.80 (20% coinsurance; deductibles pull it
-- lower; IRA inflation-adjusted coinsurance and secondary-payer cases pull single rows higher).
-- Note: CMS PUF payment amounts are before sequestration, so 0.784 is NOT expected here.
select 'row: payment > allowed' as problem, npi as key, year, payment_amt, allowed_amt
from {{ ref('fct_provider_drug_year') }}
where payment_amt > allowed_amt * 1.0001
union all
select 'national ratio out of [0.75, 0.81]', cast(year as varchar), year, sum(payment_amt), sum(allowed_amt)
from {{ ref('fct_national_drug_year') }}
where hcpcs in (select hcpcs from {{ ref('drug_catalog') }})
group by year
having sum(payment_amt) / sum(allowed_amt) not between 0.75 and 0.81
