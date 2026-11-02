-- Provider-level totals (2024): drug vs medical allowed split, risk score. No names carried forward.
select
    cast(year as int)                              as year,
    Rndrng_NPI                                     as npi,
    Rndrng_Prvdr_Type                              as provider_type,
    Rndrng_Prvdr_Ent_Cd                            as entity_code,
    Rndrng_Prvdr_State_Abrvtn                      as state_abbr,
    Rndrng_Prvdr_Zip5                              as zip5,
    cast(Tot_Benes as int)                         as benes,
    cast(Tot_Srvcs as double)                      as services,
    cast(Tot_Mdcr_Alowd_Amt as double)             as allowed_amt,
    try_cast(nullif(Drug_Mdcr_Alowd_Amt, '') as double) as drug_allowed_amt,
    try_cast(nullif(Med_Mdcr_Alowd_Amt, '') as double)  as medical_allowed_amt,
    nullif(Drug_Sprsn_Ind, '')                     as drug_suppression_ind,
    try_cast(nullif(Bene_Avg_Risk_Scre, '') as double)  as avg_risk_score
from {{ source('raw', 'provider_2024') }}
where Rndrng_Prvdr_Cntry = 'US'
