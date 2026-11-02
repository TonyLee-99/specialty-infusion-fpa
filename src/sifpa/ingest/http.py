"""HTTP helpers with retries. Every raw pull goes through here so retries and the user agent are uniform."""

from __future__ import annotations

import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (specialty-infusion-fpa; public-data research)"}
_session = requests.Session()
_session.headers.update(UA)


def get(url: str, *, params: dict | None = None, timeout: int = 120, tries: int = 4) -> requests.Response:
    """GET with exponential backoff on network errors and 429/5xx."""
    for attempt in range(tries):
        try:
            resp = _session.get(url, params=params, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{resp.status_code} for {url}")
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == tries - 1:
                raise
            time.sleep(2**attempt * 2)
    raise RuntimeError("unreachable")
