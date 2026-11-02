select
    hcpcs, status,
    cast(work_rvu as double) as work_rvu,
    cast(pe_rvu_nonfac as double) as pe_rvu_nonfac,
    cast(mp_rvu as double) as mp_rvu,
    cast(conv_factor as double) as conv_factor,
    rvu_release
from {{ source('raw', 'pfs_rvu') }}
