"""F11: the static HTML scorecard exists, is self-contained, and was screenshotted without console errors."""

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def test_scorecard_is_self_contained():
    html = (ROOT / "docs/scorecard.html").read_text()
    assert "<script src=" not in html and "https://" not in html  # no CDN, works offline
    for section in ("exec", "pricing", "forecast", "market", "variance", "rcm"):
        assert f'id="{section}"' in html
    assert "SYNTHETIC DATA" in html


def test_screenshots_exist_and_are_real_images():
    shots = json.loads((ROOT / "outputs/screenshots.json").read_text())
    assert len(shots["files"]) >= 3
    assert shots["console_errors"] == []
    for name in shots["files"]:
        img = Image.open(ROOT / "docs/img" / name)
        assert img.width >= 800 and img.height >= 300


def test_scorecard_numbers_come_from_outputs():
    html = (ROOT / "docs/scorecard.html").read_text()
    sc = json.loads((ROOT / "outputs/scenarios.json").read_text())
    base = sc["scenarios"]["base"]["administrations"]
    assert f"{base:,} infusions/yr" in html
    assert "realization" not in html.lower() and "MAPE" not in html[: html.index('id="pricing"')]  # exec page: plan numbers only
