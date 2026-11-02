"""F12: README headline numbers match the committed outputs and cannot drift."""

import json
from pathlib import Path

from sifpa import readme

ROOT = Path(__file__).resolve().parents[1]


def J(name):
    return json.loads((ROOT / "outputs" / name).read_text())


def test_readme_is_rendered_from_current_outputs():
    assert (ROOT / "README.md").read_text() == readme.build()


def test_headline_numbers_match_json_directly():
    text = (ROOT / "README.md").read_text()
    sc = J("scenarios.json")["scenarios"]
    assert f"${sc['base']['annual']['contribution']:,}" in text
    assert f"**${sc['base']['medicare_ffs_contribution_per_admin']:,.0f}**" in text
    assert f"**${sc['base']['commercial_contribution_per_admin']:,.0f}**" in text
    m = J("margin.json")
    assert f"{m['medicare_drug_margin_pct_of_drug_revenue'] * 100:.1f}%" in text
    assert f"{m['realization']['allowed_weighted_ratio_2024'] * 100:.1f}%" in text
    f = J("forecast.json")["quarterly_asp"]["mape_by_model"]
    assert f"{f['ets_damped'] * 100:.1f}%" in text and f"{f['naive'] * 100:.1f}%" in text
    mk = J("market.json")["market_top3_ohio_outside_radius"][0]
    assert mk["market"] in text


def test_readme_first_screen_has_business_output_and_says_pbip_unopened():
    text = (ROOT / "README.md").read_text()
    first = text[: text.index("## Architecture")]
    assert "Headline" in first and "docs/img/scorecard_exec.png" in first and "Executive decision memo" in first
    assert "has not been opened in Power BI Desktop" in text
    assert "SYNTHETIC" in text
