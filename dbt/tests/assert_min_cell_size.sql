-- CMS cell suppression: every provider x HCPCS row must have >= 11 beneficiaries.
select * from {{ ref('fct_provider_drug_year') }} where benes < {{ var('min_cell_benes') }}
