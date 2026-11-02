select
    mac, state as state_abbr, locality, locality_name,
    cast(pw_gpci as double) as pw_gpci, cast(pe_gpci as double) as pe_gpci, cast(mp_gpci as double) as mp_gpci
from {{ source('raw', 'pfs_gpci') }}
