-- National (all years) and region-state (2024) totals by HCPCS x place of service. Not suppressed nationally.
select
    cast(year as int)                    as year,
    Rndrng_Prvdr_Geo_Lvl                 as geo_level,
    Rndrng_Prvdr_Geo_Desc                as geo_desc,
    HCPCS_Cd                             as hcpcs,
    HCPCS_Drug_Ind = 'Y'                 as is_drug,
    Place_Of_Srvc                        as place_of_service,
    cast(Tot_Rndrng_Prvdrs as int)       as providers,
    cast(Tot_Benes as int)               as benes,
    cast(Tot_Srvcs as double)            as services,
    cast(Tot_Bene_Day_Srvcs as int)      as bene_day_services,
    cast(Avg_Mdcr_Alowd_Amt as double)   as avg_allowed,
    cast(Avg_Mdcr_Pymt_Amt as double)    as avg_payment,
    cast(Avg_Mdcr_Alowd_Amt as double) * cast(Tot_Srvcs as double) as allowed_amt,
    cast(Avg_Mdcr_Pymt_Amt as double) * cast(Tot_Srvcs as double)  as payment_amt
from {{ source('raw', 'geo_service') }}
