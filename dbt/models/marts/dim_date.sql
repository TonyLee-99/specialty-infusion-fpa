-- Daily date table for the Power BI model (marked as date table in TMDL).
select
    cast(d as date) as date,
    year(d) as year,
    quarter(d) as quarter_of_year,
    year(d) || 'Q' || quarter(d) as quarter_label,
    month(d) as month,
    strftime(d, '%b') as month_name
from generate_series(date '2013-01-01', date '2027-12-31', interval 1 day) t(d)
