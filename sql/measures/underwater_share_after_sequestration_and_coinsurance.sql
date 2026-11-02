-- SQL twin of DAX measure [Underwater Share After Sequestration and Coinsurance] (table fact_asp_quarter); context: all drugs, all quarters; DuckDB over exports/*.csv
select avg(case when payment_limit * 0.964 < asp_current then 1.0 else 0.0 end) from fact_asp_quarter where asp_current is not null
