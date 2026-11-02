-- Latest annual ('Year') county rows; falls back to the latest month if a year has no annual row yet.
with typed as (
    select
        cast(YEAR as int) as year, MONTH as month, BENE_STATE_ABRVTN as state_abbr,
        BENE_COUNTY_DESC as county_name, lpad(BENE_FIPS_CD, 5, '0') as county_fips,
        try_cast(TOT_BENES as double) as medicare_benes,
        try_cast(ORGNL_MDCR_BENES as double) as original_medicare_benes,
        try_cast(MA_AND_OTH_BENES as double) as ma_benes
    from {{ source('raw', 'medicare_enrollment_county') }}
    where BENE_FIPS_CD is not null and BENE_FIPS_CD <> ''
)
select *, original_medicare_benes / nullif(medicare_benes, 0) as ffs_share
from typed
where month = 'Year'
qualify row_number() over (partition by county_fips order by year desc) = 1
