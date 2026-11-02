"""Module 4: provider benchmarking in the 7-state region (ADR 0005).

Unit = rendering NPI (no names), peers = same specialty in the region, 2024 Medicare FFS.
KPIs: allowed per beneficiary (raw and per unit of HCC risk), services per beneficiary, drug share of
allowed, chair-infusion share of allowed, and biosimilar adoption for multi-source molecules.

Statistical honesty:
  * biosimilar rates are shrunk with an empirical-Bayes beta-binomial prior per molecule;
  * a provider whose biosimilar (or reference) row is missing may have 1-10 suppressed beneficiaries:
    that count is interval-censored to [0, 10]; the point uses 5 and the interval spans both ends;
  * "above peer" requires the 90% interval to clear the peer median, not just a high rank;
  * exported counts are always 0 or >= 11 (CMS cell rule).

`make benchmark` -> exports/fact_provider_scorecard.csv, outputs/benchmark.json
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from sifpa import engine as E
from sifpa.paths import EXPORTS, OUTPUTS

MOLECULES = ["infliximab", "rituximab", "tocilizumab", "natalizumab", "denosumab"]
SUPPRESSED_MAX = 10  # CMS removes provider x HCPCS rows with 1-10 beneficiaries


def beta_prior(x: np.ndarray, n: np.ndarray) -> tuple[float, float]:
    """Method-of-moments beta prior from observed rates, with the binomial noise removed."""
    p = x / n
    m = np.average(p, weights=n)
    var_obs = np.average((p - m) ** 2, weights=n)
    var_noise = np.mean(m * (1 - m) / n)
    var_true = max(var_obs - var_noise, 1e-6)
    k = max(m * (1 - m) / var_true - 1, 0.5)  # prior strength in pseudo-beneficiaries
    return m * k, (1 - m) * k


def shrink(x, n, a, b, level=0.90):
    lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
    post_mean = (x + a) / (n + a + b)
    return post_mean, stats.beta.ppf(lo_q, x + a, n - x + b), stats.beta.ppf(hi_q, x + a, n - x + b)


def biosimilar_table(con) -> pd.DataFrame:
    df = con.sql(f"""
        select f.npi, p.provider_type, d.molecule,
               sum(case when d.product_type = 'biosimilar' then f.benes else 0 end) as bio_benes,
               sum(case when d.product_type = 'reference' then f.benes else 0 end) as ref_benes
        from marts.fct_provider_drug_year f
        join marts.dim_drug d using (hcpcs)
        join marts.dim_provider p using (npi)
        where f.year = 2024 and f.place_of_service = 'O' and p.in_region
          and d.molecule in ({",".join(f"'{m}'" for m in MOLECULES)})
          and p.provider_type in {E.SPECIALTIES}
        group by 1, 2, 3
    """).df()
    out = []
    for _molecule, g in df.groupby("molecule"):  # one prior per molecule
        g = g.copy()
        # censored side: a missing row means 0-10 hidden beneficiaries
        g["censored"] = (g["bio_benes"] == 0) | (g["ref_benes"] == 0)
        bio, ref = g["bio_benes"].astype(float), g["ref_benes"].astype(float)
        hidden = lambda col, fill: np.where(col == 0, fill, col)  # noqa: E731
        x_low, n_low = bio, bio + hidden(ref, SUPPRESSED_MAX)              # lowest plausible rate
        x_high = hidden(bio, SUPPRESSED_MAX)
        n_high = x_high + ref                                                # highest plausible rate
        mid_x = hidden(bio, SUPPRESSED_MAX / 2)
        mid_n = mid_x + hidden(ref, SUPPRESSED_MAX / 2)
        n_lo = bio + ref
        g["raw_rate"] = g["bio_benes"] / n_lo
        uncensored = ~g["censored"]
        if uncensored.sum() >= 5:
            a, b = beta_prior(g.loc[uncensored, "bio_benes"].to_numpy(float), n_lo[uncensored].to_numpy(float))
        else:  # too few clean providers: fall back to the pooled rate with a weak prior
            m = float(mid_x.sum() / mid_n.sum())
            a, b = m * 2, (1 - m) * 2
        g["post_mean"], _, _ = shrink(mid_x, mid_n, a, b)
        _, g["ci_lo"], _ = shrink(x_low, n_low, a, b)
        _, _, g["ci_hi"] = shrink(x_high, n_high, a, b)
        g["prior_a"], g["prior_b"] = a, b
        out.append(g)
    return pd.concat(out, ignore_index=True)


def provider_kpis(con) -> pd.DataFrame:
    return con.sql(f"""
        with infusion as (
            select f.npi, sum(f.allowed_amt) as chair_allowed
            from marts.fct_provider_drug_year f
            left join marts.dim_drug d using (hcpcs)
            where f.year = 2024 and f.place_of_service = 'O'
              and (f.hcpcs_role = 'admin' or d.admin_family in ('mab_infusion', 'iv_infusion'))
            group by 1
        )
        select p.npi, p.provider_type, p.state_abbr, p.county_fips,
               p.total_benes_2024 as benes, p.total_services_2024 as services,
               p.total_allowed_2024 as allowed, p.drug_allowed_2024 as drug_allowed,
               p.avg_risk_score_2024 as risk,
               p.total_allowed_2024 / p.total_benes_2024 as allowed_per_bene,
               p.total_allowed_2024 / p.total_benes_2024 / p.avg_risk_score_2024 as allowed_per_bene_risk_adj,
               p.total_services_2024 / p.total_benes_2024 as services_per_bene,
               coalesce(p.drug_allowed_2024, 0) / p.total_allowed_2024 as drug_share,
               coalesce(i.chair_allowed, 0) / p.total_allowed_2024 as infusion_share,
               i.chair_allowed is not null as bills_chair_infusions
        from marts.dim_provider p
        left join infusion i using (npi)
        where p.in_region and p.entity_code = 'I' and p.total_benes_2024 >= 11
          and p.provider_type in {E.SPECIALTIES}
    """).df()


def market_biosimilar_share(con) -> pd.DataFrame:
    """Biosimilar share of in-office administrations by molecule: region states vs national (2024).

    Geography rows aggregate all providers, so they are far less affected by suppression than provider
    rows; this is the reliable adoption benchmark, the provider view is the noisy one."""
    return con.sql(f"""
        with g as (
            select s.state_abbr as geo, s.hcpcs, s.bene_day_services as admins
            from marts.fct_state_drug_2024 s where s.place_of_service = 'O'
            union all
            select 'US', n.hcpcs, n.bene_day_services from marts.fct_national_drug_year n
            where n.year = 2024 and n.place_of_service = 'O'
        )
        select geo, d.molecule,
               sum(case when d.product_type = 'biosimilar' then admins else 0 end) / sum(admins) as biosimilar_share,
               sum(admins) as admins
        from g join marts.dim_drug d using (hcpcs)
        where d.molecule in ({",".join(f"'{m}'" for m in MOLECULES)})
        group by 1, 2 order by 2, 1
    """).df()


def main() -> None:
    con = E.connect()
    kp = provider_kpis(con)
    for col in ("allowed_per_bene", "allowed_per_bene_risk_adj", "services_per_bene", "drug_share", "infusion_share"):
        kp[f"{col}_pctile"] = kp.groupby("provider_type")[col].rank(pct=True).round(4)
    bio = biosimilar_table(con)
    # provider-level pooled biosimilar rate across molecules (posterior means weighted by beneficiaries)
    bio["w"] = bio["bio_benes"] + bio["ref_benes"]
    pooled = bio.groupby("npi").apply(lambda g: pd.Series({
        "biosimilar_rate_shrunk": np.average(g["post_mean"], weights=g["w"]),
        "biosimilar_ci_lo": np.average(g["ci_lo"], weights=g["w"]),
        "biosimilar_ci_hi": np.average(g["ci_hi"], weights=g["w"]),
        "biosimilar_censored": bool(g["censored"].any()),
        "biosimilar_molecules": int(len(g))}), include_groups=False).reset_index()
    sc = kp.merge(pooled, on="npi", how="left")
    peer_median = sc.groupby("provider_type")["biosimilar_rate_shrunk"].transform("median")
    sc["biosimilar_vs_peer"] = np.select(
        [sc["biosimilar_ci_lo"] > peer_median, sc["biosimilar_ci_hi"] < peer_median],
        ["above_peer", "below_peer"], default=np.where(sc["biosimilar_rate_shrunk"].notna(), "not_distinguishable", ""))
    sc["biosimilar_rate_pctile"] = sc.groupby("provider_type")["biosimilar_rate_shrunk"].rank(pct=True).round(4)
    keep = ["npi", "provider_type", "state_abbr", "county_fips", "benes", "allowed_per_bene",
            "allowed_per_bene_risk_adj", "services_per_bene", "drug_share", "infusion_share", "bills_chair_infusions",
            "allowed_per_bene_pctile", "allowed_per_bene_risk_adj_pctile", "services_per_bene_pctile",
            "drug_share_pctile", "infusion_share_pctile", "biosimilar_rate_shrunk", "biosimilar_ci_lo",
            "biosimilar_ci_hi", "biosimilar_censored", "biosimilar_molecules", "biosimilar_rate_pctile",
            "biosimilar_vs_peer", "risk"]
    sc[keep].sort_values("npi").round(4).to_csv(EXPORTS / "fact_provider_scorecard.csv", index=False)
    bio_out = bio[["npi", "provider_type", "molecule", "bio_benes", "ref_benes", "censored", "raw_rate",
                   "post_mean", "ci_lo", "ci_hi"]]
    bio_out.sort_values(["npi", "molecule"]).round(4).to_csv(EXPORTS / "fact_provider_biosimilar.csv", index=False)

    # shrinkage evidence: spread of raw vs shrunk rates among small-n, uncensored providers
    clean = bio[~bio["censored"]]
    small = clean[clean["w"] < 30]
    infusers = sc[sc["bills_chair_infusions"]]
    summary = {
        "year": 2024,
        "n_providers_scored": int(len(sc)),
        "n_by_specialty": sc["provider_type"].value_counts().to_dict(),
        "n_providers_with_biosimilar_rate": int(sc["biosimilar_rate_shrunk"].notna().sum()),
        "n_provider_molecule_rates": int(len(bio)),
        "share_provider_molecule_censored": round(float(bio["censored"].mean()), 4),
        "region_biosimilar_rate_by_molecule": {
            m: round(float(g["bio_benes"].sum() / (g["bio_benes"] + g["ref_benes"]).sum()), 4)
            for m, g in bio.groupby("molecule")},
        "small_n_raw_rate_sd": round(float(small["raw_rate"].std()), 4) if len(small) > 2 else None,
        "small_n_shrunk_rate_sd": round(float(small["post_mean"].std()), 4) if len(small) > 2 else None,
        "n_small_n_uncensored": int(len(small)),
        "biosimilar_vs_peer_counts": sc["biosimilar_vs_peer"].replace("", "no_rate").value_counts().to_dict(),
        "naive_top_quartile_biosimilar": int((sc["biosimilar_rate_pctile"] >= 0.75).sum()),
        "median_by_specialty": sc.groupby("provider_type")[["allowed_per_bene", "allowed_per_bene_risk_adj",
                                                             "services_per_bene", "drug_share", "infusion_share"]]
        .median().round(4).to_dict(orient="index"),
        "infusing_providers": int(len(infusers)),
        "infusing_median_drug_share": round(float(infusers["drug_share"].median()), 4),
        "infusing_median_infusion_share": round(float(infusers["infusion_share"].median()), 4),
        "rheum_infusing_median_drug_share": round(float(
            infusers[infusers["provider_type"] == "Rheumatology"]["drug_share"].median()), 4),
    }
    mkt = market_biosimilar_share(con)
    mkt.round(4).to_csv(EXPORTS / "fact_market_biosimilar_share.csv", index=False)
    summary["market_biosimilar_share_2024"] = {
        m: {r.geo: round(float(r.biosimilar_share), 4) for r in g.itertuples()} for m, g in mkt.groupby("molecule")}
    (OUTPUTS / "benchmark.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
