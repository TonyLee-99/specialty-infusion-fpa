"""F08: white-space ranking covers the region, is scored at market grain, and is stress-tested."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from sifpa import market as MK

ROOT = Path(__file__).resolve().parents[1]


def test_every_region_county_is_present():
    c = pd.read_csv(ROOT / "exports/dim_county_market.csv", dtype={"county_fips": str})
    assert len(c) == 607  # OH 88, IL 102, IN 92, KY 120, MI 83, PA 67, WV 55
    assert c["population"].gt(0).all() and c["arthritis_prev"].between(0.05, 0.6).all()


def test_markets_partition_counties():
    c = pd.read_csv(ROOT / "exports/dim_county_market.csv", dtype={"county_fips": str})
    m = pd.read_csv(ROOT / "exports/dim_market.csv")
    assert m["population"].sum() == c["population"].sum()
    assert m["n_counties"].sum() == len(c)


def test_ranked_only_if_eligible_and_ranks_are_a_permutation():
    m = pd.read_csv(ROOT / "exports/dim_market.csv")
    ranked = m.dropna(subset=["rank"])
    assert ranked["eligible"].all()
    assert sorted(ranked["rank"].astype(int)) == list(range(1, len(ranked) + 1))


def test_weight_sensitivity_reported():
    s = json.loads((ROOT / "outputs/market.json").read_text())
    assert s["n_weight_draws"] >= 1000
    assert 0 <= s["markets"]["mean_top10_overlap_random_weights"] <= 1
    assert all(0 <= r["p_top10"] <= 1 for r in s["market_top10"])


def test_existing_site_market_is_flagged():
    m = pd.read_csv(ROOT / "exports/dim_market.csv")
    columbus = m[m["market_name"].str.startswith("Columbus, OH")]
    assert columbus["cannibalization_flag"].all()


def test_haversine_sanity():
    # Columbus -> Cleveland is ~125 miles as the crow flies
    d = MK.haversine_miles(39.96, -83.00, 41.50, -81.69)
    assert 115 < d < 135


def test_zscore_is_standardised():
    z = MK.zscore(pd.Series(np.arange(10.0)))
    assert abs(z.mean()) < 1e-12 and abs(z.std(ddof=0) - 1) < 1e-12
