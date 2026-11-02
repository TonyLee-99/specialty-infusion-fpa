-- Back out the ASP behind each published payment limit (ADR 0003).
--   reference / single source: PL = 1.06 * ASP(t-2)              -> ASP = PL / 1.06
--   biosimilar:                PL = ASP_bio(t-2) + k * ASP_ref(t-2), k = 8% if flagged else 6%
-- Rows priced by a non-ASP rule ("lesser of", AMP-based) get no implied ASP.
-- Biosimilars join to their reference code (seed column reference_hcpcs). Ustekinumab biosimilars are
-- AMBIGUOUS: their reference blends Stelara subq (J3357, retired 2025Q2) and IV (J3358), so no math.
with pl as (
    select a.*, d.molecule, d.product_type, d.reference_hcpcs
    from {{ ref('stg_asp_payment_limits') }} a
    join {{ ref('drug_catalog') }} d using (hcpcs)
),
ref_pl as (
    select payment_quarter, hcpcs as reference_hcpcs, payment_limit as ref_payment_limit,
           (flag_lesser_of or flag_amp_based) as ref_not_asp_based
    from {{ ref('stg_asp_payment_limits') }}
)
select
    pl.payment_quarter,
    pl.quarter_start,
    pl.hcpcs,
    pl.molecule,
    pl.product_type,
    pl.payment_limit,
    pl.coinsurance_pct,
    pl.notes,
    pl.flag_addon_8pct,
    pl.flag_lesser_of,
    pl.flag_amp_based,
    case when pl.product_type = 'biosimilar' and pl.flag_addon_8pct then {{ var('biosimilar_irapct') }}
         else {{ var('asp_addon_pct') }} end                          as addon_pct,
    case when r.ref_not_asp_based then null
         else r.ref_payment_limit / (1 + {{ var('asp_addon_pct') }}) end as ref_asp,
    case
        when pl.flag_lesser_of or pl.flag_amp_based then null
        when pl.product_type in ('reference', 'single_source')
            then pl.payment_limit / (1 + {{ var('asp_addon_pct') }})
        when r.ref_not_asp_based or r.ref_payment_limit is null then null
        else pl.payment_limit
             - (case when pl.flag_addon_8pct then {{ var('biosimilar_irapct') }} else {{ var('asp_addon_pct') }} end)
               * r.ref_payment_limit / (1 + {{ var('asp_addon_pct') }})
    end                                                               as implied_asp
from pl
left join ref_pl r using (payment_quarter, reference_hcpcs)
