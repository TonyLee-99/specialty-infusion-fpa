"""data.cms.gov: resolve one dataset uuid per year from the public catalog, then page through filtered rows."""

from __future__ import annotations

import json
import re
from functools import lru_cache

import pandas as pd

from sifpa.ingest.http import get
from sifpa.paths import RAW

CATALOG_URL = "https://data.cms.gov/data.json"
API = "https://data.cms.gov/data-api/v1/dataset/{uuid}/data"
PAGE = 5000  # API maximum page size


@lru_cache(maxsize=1)
def catalog() -> list[dict]:
    cache = RAW / "_cms_catalog.json"
    if not cache.exists():
        cache.write_bytes(get(CATALOG_URL, timeout=300).content)
    return json.loads(cache.read_text())["dataset"]


def dataset_uuids(title_prefix: str) -> dict[int, str]:
    """Map year -> API uuid for a dataset family. When a year has several API versions, the
    catalog lists the newest last, so the last one wins."""
    out: dict[int, str] = {}
    for ds in catalog():
        if not ds["title"].startswith(title_prefix + " :"):
            continue
        year = int(ds["temporal"][0]["startDate"][:4]) if isinstance(ds.get("temporal"), list) else int(
            re.search(r"(\d{4})", ds["title"]).group(1))
        for dist in ds.get("distribution", []):
            url = dist.get("accessURL") or ""
            m = re.search(r"/dataset/([0-9a-f-]{36})/data$", url)
            if m:
                out[year] = m.group(1)
    return dict(sorted(out.items()))


def fetch(uuid: str, filters: dict[str, str] | None = None) -> pd.DataFrame:
    """Page through `filter[col]=value` results. Returns every column as string (CMS API style)."""
    params = {f"filter[{k}]": v for k, v in (filters or {}).items()}
    rows, offset = [], 0
    while True:
        batch = get(API.format(uuid=uuid), params={**params, "size": PAGE, "offset": offset}).json()
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    return pd.DataFrame(rows)
