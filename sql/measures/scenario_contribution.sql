-- SQL twin of DAX measure [Scenario Contribution] (table fact_scenarios); context: scenario = policy_2028; DuckDB over exports/*.csv
select sum(value) from fact_scenarios where scenario = 'policy_2028' and metric = 'contribution'
