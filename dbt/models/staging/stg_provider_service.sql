-- Provider x HCPCS x place of service x year. CMS drops rows with < 11 beneficiaries.
select
    cast(year as int)                          as year,
    Rndrng_NPI                                 as npi,
    Rndrng_Prvdr_Type                          as provider_type,
    Rndrng_Prvdr_Ent_Cd                        as entity_code,
    Rndrng_Prvdr_State_Abrvtn                  as state_abbr,
    Rndrng_Prvdr_Zip5                          as zip5,
    try_cast(Rndrng_Prvdr_RUCA as double)      as ruca,
    HCPCS_Cd                                   as hcpcs,
    Place_Of_Srvc                              as place_of_service,
    cast(Tot_Benes as int)                     as benes,
    cast(Tot_Srvcs as double)                  as services,
    cast(Tot_Bene_Day_Srvcs as int)            as bene_day_services,
    cast(Avg_Mdcr_Alowd_Amt as double)         as avg_allowed,
    cast(Avg_Mdcr_Pymt_Amt as double)          as avg_payment,
    cast(Avg_Mdcr_Alowd_Amt as double) * cast(Tot_Srvcs as double) as allowed_amt,
    cast(Avg_Mdcr_Pymt_Amt as double) * cast(Tot_Srvcs as double)  as payment_amt
from {{ source('raw', 'provider_service') }}
where Rndrng_Prvdr_Cntry = 'US'
