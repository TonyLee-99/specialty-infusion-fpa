-- SQL twin of DAX measure [IRA 8pct Add-on Codes Latest] (table fact_asp_quarter); runs on DuckDB over exports/*.csv
select count(*) from fact_asp_quarter where flag_addon_8pct and quarter_start = (select max(quarter_start) from fact_asp_quarter)
