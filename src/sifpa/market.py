"""Module 5: white-space ranking for the next comprehensive-care site (7-state region).

Grain: the market (metro/micro CBSA; a county outside any CBSA stands alone). Counties are the wrong
unit for a site decision because suburbs borrow specialists from the core county next door; the
county table is kept as detail.

Demand  : adults with arthritis (CDC PLACES prevalence x Census PEP adults), Original Medicare
          beneficiaries (CMS enrollment): the buy-and-bill FFS pool.
Supply  : rheum / neuro / GI / allergy clinicians billing Medicare (2024) and providers billing chair
          infusions of the catalog drugs in an office (2024), per 100k, mapped to county by ZIP->ZCTA.
Score   : weighted z-scores (weights in config/assumptions.yaml); counties under the population screen are
          not ranked; counties near the Columbus site are flagged for cannibalisation.
Stability: 2,000 Dirichlet(1,1,1,1) weightings -> P(top 10) per county and mean top-10 overlap.

`make market` -> exports/dim_county_market.csv, outputs/market.json
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from sifpa import assumptions as A
from sifpa import engine as E
from sifpa.paths import EXPORTS, OUTPUTS

COMPONENTS = ["market_size", "medicare_ffs", "specialist_gap", "infusion_gap"]
N_DRAWS = 2000


def county_frame(con) -> pd.DataFrame:
    return con.sql(f"""
        with spec as (
            select county_fips, count(*) as specialists,
                   count(*) filter (where provider_type = 'Rheumatology') as rheumatologists,
                   count(*) filter (where provider_type = 'Neurology') as neurologists
            from marts.dim_provider
            where entity_code = 'I' and total_benes_2024 >= 11 and provider_type in {E.SPECIALTIES}
            group by 1
        ),
        inf as (
            select p.county_fips, count(distinct f.npi) as infusion_billers,
                   sum(f.bene_day_services) as infusion_admins
            from marts.fct_provider_drug_year f
            join marts.dim_drug d using (hcpcs)
            join marts.dim_provider p using (npi)
            where f.year = 2024 and f.place_of_service = 'O' and d.admin_family in ('mab_infusion', 'iv_infusion')
            group by 1
        )
        select c.county_fips, c.county_name, c.state_abbr, c.market_id, c.market_name, c.market_type,
               c.market_counties_total, c.population, c.pop_18plus, c.pop_65plus,
               c.arthritis_prev, c.arthritis_prev * c.pop_18plus as arthritis_adults,
               c.medicare_benes, c.original_medicare_benes as ffs_benes, c.ffs_share, c.lat, c.lon,
               coalesce(s.specialists, 0) as specialists, coalesce(s.rheumatologists, 0) as rheumatologists,
               coalesce(s.neurologists, 0) as neurologists,
               coalesce(i.infusion_billers, 0) as infusion_billers, coalesce(i.infusion_admins, 0) as infusion_admins
        from marts.dim_county c
        left join spec s using (county_fips)
        left join inf i using (county_fips)
    """).df()


def haversine_miles(lat1, lon1, lat2, lon2):
    r = 3958.8
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat, dlon = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def zscore(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / s.std(ddof=0)


def components(df: pd.DataFrame) -> pd.DataFrame:
    """Higher = more attractive for every component (gaps are signed so that less supply scores higher)."""
    c = pd.DataFrame(index=df.index)
    c["market_size"] = zscore(np.log(df["arthritis_adults"]))
    c["medicare_ffs"] = zscore(np.log(df["ffs_benes"]))
    c["specialist_gap"] = zscore(np.log(df["arthritis_adults"] / (df["specialists"] + 1)))
    c["infusion_gap"] = -zscore(df["infusion_billers"] / df["population"] * 1e5)
    return c


SUMS = ["population", "pop_18plus", "pop_65plus", "arthritis_adults", "medicare_benes", "ffs_benes",
        "specialists", "rheumatologists", "neurologists", "infusion_billers", "infusion_admins"]


def to_markets(counties: pd.DataFrame, site_fips: str) -> pd.DataFrame:
    """Sum counts to market grain; location = population-weighted centroid of member counties."""
    c = counties.assign(wlat=counties["lat"] * counties["population"], wlon=counties["lon"] * counties["population"],
                        has_site=counties["county_fips"] == site_fips)
    g = c.groupby(["market_id", "market_name", "market_type"])
    m = g[SUMS + ["wlat", "wlon"]].sum()
    m["has_site"] = g["has_site"].any()
    m["n_counties"] = g.size()
    # CBSAs that cross out of the 7-state region (e.g. St. Louis MO-IL) are scored on their in-region part
    m["partial_market"] = m["n_counties"] < g["market_counties_total"].first()
    m["states"] = g["state_abbr"].agg(lambda s: "/".join(sorted(set(s))))
    m["lat"], m["lon"] = m["wlat"] / m["population"], m["wlon"] / m["population"]
    return m.drop(columns=["wlat", "wlon"]).reset_index()


def score(df: pd.DataFrame, cfg: dict, site_lat: float, site_lon: float, rng) -> tuple[pd.DataFrame, dict]:
    """Add per-capita supply, eligibility, cannibalisation flag, weighted score, rank and P(top 10)."""
    df = df.copy()
    df["miles_to_columbus_site"] = haversine_miles(df["lat"], df["lon"], site_lat, site_lon)
    df["specialists_per_100k"] = df["specialists"] / df["population"] * 1e5
    df["infusion_billers_per_100k"] = df["infusion_billers"] / df["population"] * 1e5
    df["infusion_admins_per_1k_ffs"] = df["infusion_admins"] / df["ffs_benes"] * 1e3
    df["eligible"] = df["population"] >= cfg["min_population"]["value"]
    df["cannibalization_flag"] = (df["miles_to_columbus_site"] < cfg["cannibalization_miles"]["value"]) | df["has_site"]
    el = df[df["eligible"]].copy()
    comp = components(el)
    w = cfg["weights"]["value"]
    el["score"] = sum(w[k] * comp[k] for k in COMPONENTS)
    for k in COMPONENTS:
        el[f"z_{k}"] = comp[k]
    el["rank"] = el["score"].rank(ascending=False, method="first").astype(int)
    draws = rng.dirichlet(np.ones(len(COMPONENTS)), size=N_DRAWS)
    ranks = (-(comp[COMPONENTS].to_numpy() @ draws.T)).argsort(axis=0).argsort(axis=0) + 1
    el["p_top10"] = (ranks <= 10).mean(axis=1)
    el["median_rank_random_weights"] = np.median(ranks, axis=1)
    base_top10 = set(el.index[el["rank"] <= 10])
    idx = el.index.to_numpy()
    overlap = float(np.mean([len(base_top10 & set(idx[ranks[:, j] <= 10])) / 10 for j in range(N_DRAWS)]))
    cols = ["score", "rank", "p_top10", "median_rank_random_weights"] + [f"z_{k}" for k in COMPONENTS]
    return df.join(el[cols]), {"n_eligible": int(len(el)), "mean_top10_overlap_random_weights": round(overlap, 4),
                               "n_p_top10_over_half": int((el["p_top10"] > 0.5).sum())}


def main() -> None:
    con = E.connect()
    cfg = A.load()["market"]
    rng = np.random.default_rng(20261102)
    site_fips = cfg["existing_site_county_fips"]["value"]
    counties = county_frame(con)
    site = counties[counties["county_fips"] == site_fips].iloc[0]
    markets, m_stats = score(to_markets(counties, site_fips), cfg, site["lat"], site["lon"], rng)
    markets.sort_values("market_id").round(4).to_csv(EXPORTS / "dim_market.csv", index=False)
    counties_scored, c_stats = score(counties.assign(has_site=counties["county_fips"] == site_fips), cfg,
                                     site["lat"], site["lon"], rng)
    counties_scored.drop(columns=["has_site"]).sort_values("county_fips").round(4).to_csv(
        EXPORTS / "dim_county_market.csv", index=False)
    df, w = counties_scored, cfg["weights"]["value"]
    el = df[df["eligible"]]
    ranked = el.sort_values("rank")
    outside = ranked[~ranked["cannibalization_flag"]]
    mk = markets[markets["eligible"]].sort_values("rank")
    mk_out = mk[~mk["cannibalization_flag"]]
    top_m = lambda d, n: [  # noqa: E731
        {"market": r.market_name, "market_id": r.market_id, "states": r.states, "rank": int(r.rank),
         "score": round(float(r.score), 3), "p_top10": round(float(r.p_top10), 3),
         "median_rank_random_weights": float(r.median_rank_random_weights),
         "population": int(r.population), "arthritis_adults": int(r.arthritis_adults), "ffs_benes": int(r.ffs_benes),
         "specialists_per_100k": round(float(r.specialists_per_100k), 1),
         "rheumatologists": int(r.rheumatologists),
         "infusion_billers_per_100k": round(float(r.infusion_billers_per_100k), 2),
         "miles_to_columbus_site": round(float(r.miles_to_columbus_site)),
         "cannibalization_flag": bool(r.cannibalization_flag), "partial_market": bool(r.partial_market)}
        for r in d.head(n).itertuples()]
    top = lambda d, n: [  # noqa: E731
        {"county": f"{r.county_name}, {r.state_abbr}", "fips": r.county_fips, "rank": int(r.rank),
         "score": round(float(r.score), 3), "p_top10": round(float(r.p_top10), 3),
         "population": int(r.population), "arthritis_adults": int(r.arthritis_adults),
         "ffs_benes": int(r.ffs_benes), "specialists_per_100k": round(float(r.specialists_per_100k), 1),
         "infusion_billers_per_100k": round(float(r.infusion_billers_per_100k), 2),
         "miles_to_columbus_site": round(float(r.miles_to_columbus_site)), "cannibalization_flag": bool(r.cannibalization_flag)}
        for r in d.head(n).itertuples()]
    summary = {
        "grain": "market (CBSA or stand-alone county)",
        "n_markets": int(len(markets)), "markets": m_stats,
        "market_top10": top_m(mk, 10),
        "market_top5_outside_cannibalization_radius": top_m(mk_out, 5),
        "market_top3_ohio_outside_radius": top_m(mk_out[mk_out["states"].str.contains("OH")], 3),
        "n_counties": int(len(df)), "counties": c_stats, "weights": w, "n_weight_draws": N_DRAWS,
        "county_top10": top(ranked, 10),
        "top5_outside_cannibalization_radius": top(outside, 5),
        "ohio_top3_outside_radius": top(outside[outside["state_abbr"] == "OH"], 3),
        "region_specialists_per_100k_median": round(float(df["specialists_per_100k"].median()), 2),
        "counties_with_zero_specialists": int((df["specialists"] == 0).sum()),
    }
    (OUTPUTS / "market.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["markets"], indent=1))
    for r in summary["market_top10"]:
        print(r)
    print("ohio:", [(r["market"], r["rank"], r["p_top10"]) for r in summary["market_top3_ohio_outside_radius"]])


if __name__ == "__main__":
    main()
