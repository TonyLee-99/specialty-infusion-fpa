-- Drug dimension: seed catalog + the latest CMS short descriptor and billing unit.
with latest as (
    select hcpcs, short_desc, dosage
    from {{ ref('stg_asp_payment_limits') }}
    qualify row_number() over (partition by hcpcs order by quarter_start desc) = 1
)
select
    d.hcpcs, d.molecule, d.brand, d.product_type, d.therapeutic_area, d.admin_family,
    d.formulary_listed = 'Y' as formulary_listed,
    d.ipay2028_selected = 'Y' as ipay2028_selected,
    d.product_type = 'biosimilar' as is_biosimilar,
    d.molecule in (select molecule from {{ ref('drug_catalog') }} where product_type = 'biosimilar') as is_multisource,
    l.short_desc as cms_short_desc,
    l.dosage as billing_unit
from {{ ref('drug_catalog') }} d
left join latest l using (hcpcs)
