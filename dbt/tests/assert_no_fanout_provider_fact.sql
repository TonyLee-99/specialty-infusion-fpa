-- Join fan-out guard: the provider fact must have exactly as many rows as the filtered staging rows.
with s as (
    select count(*) as n from {{ ref('stg_provider_service') }}
    where hcpcs in (select hcpcs from {{ ref('drug_catalog') }})
       or hcpcs in (select hcpcs from {{ ref('admin_codes') }})
),
f as (select count(*) as n from {{ ref('fct_provider_drug_year') }})
select s.n as staging_rows, f.n as fact_rows from s, f where s.n <> f.n
