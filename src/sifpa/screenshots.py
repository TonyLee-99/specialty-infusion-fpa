"""`make screenshots`: headless Chromium renders docs/scorecard.html and captures each report page.

Fails if the page logs any console error. Writes docs/img/scorecard_<section>.png and
outputs/screenshots.json (file list + console error count).
"""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

from sifpa.paths import DOCS, IMG, OUTPUTS

SECTIONS = ["exec", "pricing", "forecast", "market", "variance", "rcm"]


def main() -> None:
    errors: list[str] = []
    shots = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1180, "height": 900}, device_scale_factor=1.5,
                                color_scheme="light")
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto((DOCS / "scorecard.html").as_uri())
        page.wait_for_load_state("load")
        for sec in SECTIONS:
            out = IMG / f"scorecard_{sec}.png"
            page.locator(f"#{sec}").screenshot(path=str(out))
            shots.append(out.name)
        browser.close()
    (OUTPUTS / "screenshots.json").write_text(json.dumps({"files": shots, "console_errors": errors}, indent=2) + "\n")
    if errors:
        raise SystemExit(f"console errors: {errors}")
    print("screenshots:", shots)


if __name__ == "__main__":
    main()
