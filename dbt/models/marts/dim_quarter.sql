select
    year || 'Q' || q as quarter_label,
    make_date(year, (q - 1) * 3 + 1, 1) as quarter_start,
    year, q as quarter_of_year
from range(2013, 2029) t(year), range(1, 5) s(q)
