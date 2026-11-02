"""F08/F20: market-grain ranking without double counting, with a prescriber floor and whole metros."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from sifpa import market as MK

ROOT = Path(__file__).resolve().parents[1]


def test_region_counties_and_crossing_metros_are_present():
    c = pd.read_csv(ROOT / "exports/dim_county_market.csv", dtype={"county_fips": str})
    assert c["in_region"].sum() == 607
    assert (~c["in_region"]).sum() > 0  # e.g. St. Louis MO counties
    m = pd.read_csv(ROOT / "exports/dim_market.csv")
    stl = m[m["market_name"].str.startswith("St. Louis")]
    assert "MO" in stl["states"].iloc[0]


def test_markets_partition_counties():
    c = pd.read_csv(ROOT / "exports/dim_county_market.csv")
    m = pd.read_csv(ROOT / "exports/dim_market.csv")
    assert m["population"].sum() == c["population"].sum() and m["n_counties"].sum() == len(c)


def test_no_double_counted_components_and_prescriber_floor():
    s = json.loads((ROOT / "outputs/market.json").read_text())
    corr = pd.DataFrame(s["markets"]["component_correlation"])
    off = corr.where(~np.eye(len(corr), dtype=bool)).abs().max().max()
    assert off < 0.9
    m = pd.read_csv(ROOT / "exports/dim_market.csv")
    ranked = m.dropna(subset=["rank"])
    assert ((ranked["rheumatologists"] + ranked["neurologists"]) >= 5).all()
    assert sorted(ranked["rank"].astype(int)) == list(range(1, len(ranked) + 1))


def test_weight_sensitivity_reported_with_honest_name():
    s = json.loads((ROOT / "outputs/market.json").read_text())
    assert s["n_weight_draws"] >= 1000
    assert all("share_of_weightings_in_top10" in r for r in s["market_top10"])


def test_existing_site_market_is_flagged():
    m = pd.read_csv(ROOT / "exports/dim_market.csv")
    assert m[m["market_name"].str.startswith("Columbus, OH")]["cannibalization_flag"].all()


def test_haversine_sanity():
    assert 115 < MK.haversine_miles(39.96, -83.00, 41.50, -81.69) < 135
