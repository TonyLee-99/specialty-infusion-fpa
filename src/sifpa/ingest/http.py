"""HTTP helpers with retries. Every raw pull goes through here so retries and the user agent are uniform."""

from __future__ import annotations

import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (specialty-infusion-fpa; public-data research)"}
_session = requests.Session()
_session.headers.update(UA)


class _ClientError(Exception):
    pass


class _RetryAfter(Exception):
    def __init__(self, seconds: float):
        super().__init__(f"retry after {seconds}s")
        self.seconds = seconds


def get(url: str, *, params: dict | None = None, timeout: int = 120, tries: int = 8,
        headers: dict | None = None) -> requests.Response:
    """GET with exponential backoff on network errors and 429/5xx (honours Retry-After).

    data.cms.gov rate-limits bursts (a second full pull within the hour hit HTTP 429), so the wait
    grows to ~2 minutes before giving up."""
    for attempt in range(tries):
        try:
            resp = _session.get(url, params=params, timeout=timeout, headers=headers)
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = resp.headers.get("Retry-After")
                raise requests.HTTPError(f"{resp.status_code} for {url}", response=resp) if not wait else \
                    _RetryAfter(float(wait) if wait.replace(".", "").isdigit() else 30.0)
            if 400 <= resp.status_code < 500:  # 403/404 will not fix themselves: fail fast, no retries
                raise _ClientError(f"{resp.status_code} for {url}")
            return resp
        except _RetryAfter as ra:
            if attempt == tries - 1:
                raise
            time.sleep(min(ra.seconds, 120))
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == tries - 1:
                raise
            time.sleep(min(2**attempt * 3, 120))
    raise RuntimeError("unreachable")
