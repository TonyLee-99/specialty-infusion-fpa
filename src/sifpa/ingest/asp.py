"""CMS quarterly ASP payment-limit files (2017Q1-latest) -> one long table.

The CMS page links each quarter's zip under several naming conventions. Pre-2021 links go through
the CMS/AMA CPT license page; we take the underlying file path and keep only HCPCS Level II J/Q codes
(no CPT descriptors are stored or committed).
"""

from __future__ import annotations

import csv
import io
import re
import zipfile

import pandas as pd

from sifpa.ingest.http import get

PAGE_URL = "https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files"
MONTHS = {"jan": 1, "january": 1, "apr": 4, "april": 4, "jul": 7, "july": 7, "oct": 10, "october": 10}
FIRST_YEAR = 2017


def quarter_links(html: str) -> dict[str, str]:
    """Return {'2026Q4': absolute_url} for payment-limit (pricing) zips, newest version per quarter."""
    links: dict[str, str] = {}
    for href in re.findall(r'href="([^"]+\.zip)"', html):
        low = href.lower()
        if not ("pricing" in low or "payment-limit" in low) or any(
            bad in low for bad in ("noc", "crosswalk", "vaccine", "awp", "opps")
        ):
            continue
        # License-page links wrap the real path in ?file=...
        path = href.split("file=", 1)[1] if "file=" in href else href
        url = path if path.startswith("http") else "https://www.cms.gov" + path
        name = path.rsplit("/Downloads/", 1)[-1].lower()
        m_year = re.search(r"(20\d\d)", name)
        m_month = re.search(r"(january|april|july|october|jan|apr|jul|oct)", name)
        if not (m_year and m_month):
            continue
        year, month = int(m_year.group(1)), MONTHS[m_month.group(1)]
        if year < FIRST_YEAR:
            continue
        key = f"{year}Q{(month - 1) // 3 + 1}"
        # Later links on the page / "final" / "updated" versions supersede earlier ones.
        if key not in links or any(w in low for w in ("final", "updated")):
            links[key] = url
    return dict(sorted(links.items()))


def _read_rows(zf: zipfile.ZipFile) -> list[list[str]]:
    """Prefer the section-508 CSV; fall back to the .xls/.xlsx payment-limit sheet."""
    names = zf.namelist()
    csvs = [n for n in names if n.lower().endswith(".csv") and "not payable" not in n.lower()]
    if csvs:
        raw = zf.read(csvs[0])
        text = raw.decode("utf-8-sig", errors="replace") if b"\xef\xbb\xbf" in raw[:3] else raw.decode("latin-1")
        return list(csv.reader(io.StringIO(text, newline="")))
    xls = [n for n in names if n.lower().endswith((".xls", ".xlsx")) and "not payable" not in n.lower()]
    df = pd.read_excel(io.BytesIO(zf.read(xls[0])), header=None, dtype=str)
    return df.fillna("").values.tolist()


def parse_zip(content: bytes, quarter: str) -> pd.DataFrame:
    zf = zipfile.ZipFile(io.BytesIO(content))
    rows = _read_rows(zf)
    hdr_i = next(i for i, r in enumerate(rows) if r and str(r[0]).strip().lower() == "hcpcs code")
    header = [str(h).strip().lower() for h in rows[hdr_i]]
    note_line = " ".join(" ".join(map(str, r)) for r in rows[:hdr_i])
    basis = re.search(r"based on (\d)Q(\d\d) ASP data", note_line)

    def col(name: str) -> int | None:
        return next((j for j, h in enumerate(header) if h.startswith(name)), None)

    c_code, c_desc, c_dose, c_pl = col("hcpcs code"), col("short description"), col("hcpcs code dosage"), col("payment limit")
    c_coins, c_notes = col("co-insurance"), col("notes")
    out = []
    for r in rows[hdr_i + 1 :]:
        if not r or not str(r[c_code]).strip():
            continue
        code = str(r[c_code]).strip().upper()
        if not re.fullmatch(r"[JQ]\d{4}", code):  # HCPCS Level II drug codes only (no CPT content)
            continue
        out.append(
            {
                "quarter": quarter,
                "hcpcs": code,
                "short_desc": str(r[c_desc]).strip(),
                "dosage": str(r[c_dose]).strip(),
                "payment_limit": str(r[c_pl]).strip(),
                "coinsurance_pct": str(r[c_coins]).strip() if c_coins is not None and c_coins < len(r) else "",
                "notes": str(r[c_notes]).strip() if c_notes is not None and c_notes < len(r) else "",
                "asp_basis_quarter": f"20{basis.group(2)}Q{basis.group(1)}" if basis else "",
            }
        )
    return pd.DataFrame(out)


def pull() -> tuple[pd.DataFrame, list[str]]:
    links = quarter_links(get(PAGE_URL).text)
    frames = [parse_zip(get(url).content, q) for q, url in links.items()]
    return pd.concat(frames, ignore_index=True), list(links.values())
