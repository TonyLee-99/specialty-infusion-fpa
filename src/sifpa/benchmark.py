"""Module 4: provider benchmarking in the 7-state region (ADR 0005, revision 1).

Unit = rendering NPI (no names), peers = same specialty in the region, 2024 Medicare FFS.
KPIs: allowed per beneficiary (raw and per unit of HCC risk), services per beneficiary, drug share of
allowed, chair-infusion share of allowed, with percentile ranks within specialty.

Biosimilar adoption is where CMS suppression bites, so it is handled at the right grain:
  * eligible codes = products of the molecule that had ANY national in-office Medicare use that year
    (no denosumab or natalizumab biosimilar existed in 2024 -> structural zero, not hidden patients);
  * each eligible code missing from a provider's rows hides 0-10 beneficiaries (CMS cell rule), so the
    provider's biosimilar share of beneficiary-code pairs is an INTERVAL [lo, hi], not a point;
  * beneficiaries are not de-duplicated across codes (switchers count twice), so the share is stated
    as "share of beneficiary-code pairs";
  * no empirical-Bayes shrinkage: almost no provider is fully observed, so a prior cannot be estimated
    (the first version silently fell back to a weak prior for every molecule);
  * a provider is "above/below its state" only if the whole interval clears the state's (unsuppressed)
    biosimilar share; intervals wider than 0.40 are "insufficient data".
`make benchmark` -> exports/fact_provider_scorecard.csv, exports/fact_provider_biosimilar.csv,
                    exports/fact_market_biosimilar_share.csv, outputs/benchmark.json
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from sifpa import engine as E
from sifpa.paths import EXPORTS, OUTPUTS

MOLECULES = ["infliximab", "rituximab", "tocilizumab", "natalizumab", "denosumab"]
SUPPRESSED_MAX = 10  # CMS removes provider x HCPCS rows with 1-10 beneficiaries
MAX_WIDTH = 0.40


def eligible_codes(con, year: int = 2024) -> pd.DataFrame:
    """Products of each molecule with national in-office use in `year` (structural availability)."""
    return con.sql(f"""
        select d.molecule, d.hcpcs, d.product_type
        from marts.fct_national_drug_year n join marts.dim_drug d using (hcpcs)
        where n.year = {year} and n.place_of_service = 'O' and n.benes > 0
          and d.molecule in ({",".join(f"'{m}'" for m in MOLECULES)})
    """).df()


def state_bene_share(con) -> pd.DataFrame:
    return con.sql(f"""
        select s.state_abbr, d.molecule,
               sum(case when d.product_type = 'biosimilar' then s.benes else 0 end) / sum(s.benes) as state_share
        from marts.fct_state_drug_2024 s join marts.dim_drug d using (hcpcs)
        where s.place_of_service = 'O' and d.molecule in ({",".join(f"'{m}'" for m in MOLECULES)})
        group by 1, 2
    """).df()


def biosimilar_intervals(con) -> pd.DataFrame:
    elig = eligible_codes(con)
    multi = elig.groupby("molecule")["product_type"].apply(lambda s: (s == "biosimilar").any())
    mols = multi[multi].index.tolist()  # molecules with a marketed biosimilar that year
    rows = con.sql(f"""
        select f.npi, p.provider_type, p.state_abbr, d.molecule, f.hcpcs, d.product_type, f.benes
        from marts.fct_provider_drug_year f
        join marts.dim_drug d using (hcpcs) join marts.dim_provider p using (npi)
        where f.year = 2024 and f.place_of_service = 'O' and p.in_region and p.provider_type in {E.SPECIALTIES}
          and d.molecule in ({",".join(f"'{m}'" for m in mols)})
    """).df()
    out = []
    for (npi, mol), g in rows.groupby(["npi", "molecule"]):
        e = elig[elig["molecule"] == mol]
        seen = set(g["hcpcs"])
        b_vis = g.loc[g["product_type"] == "biosimilar", "benes"].sum()
        r_vis = g.loc[g["product_type"] != "biosimilar", "benes"].sum()
        m_b = int(((e["product_type"] == "biosimilar") & ~e["hcpcs"].isin(seen)).sum())
        m_r = int(((e["product_type"] != "biosimilar") & ~e["hcpcs"].isin(seen)).sum())
        lo = b_vis / (b_vis + r_vis + SUPPRESSED_MAX * m_r)
        hi = (b_vis + SUPPRESSED_MAX * m_b) / (b_vis + SUPPRESSED_MAX * m_b + r_vis)
        out.append({"npi": npi, "provider_type": g["provider_type"].iloc[0], "state_abbr": g["state_abbr"].iloc[0],
                    "molecule": mol, "bio_benes_visible": int(b_vis), "ref_benes_visible": int(r_vis),
                    "missing_biosimilar_codes": m_b, "missing_reference_codes": m_r,
                    "fully_observed": m_b + m_r == 0, "share_lo": lo, "share_hi": hi})
    df = pd.DataFrame(out).merge(state_bene_share(con), on=["state_abbr", "molecule"], how="left")
    df["width"] = df["share_hi"] - df["share_lo"]
    df["vs_state"] = np.select(
        [df["width"] > MAX_WIDTH, df["share_lo"] > df["state_share"], df["share_hi"] < df["state_share"]],
        ["insufficient_data", "above_state", "below_state"], default="not_distinguishable")
    return df


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
    Geography rows aggregate all providers: the reliable adoption benchmark."""
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
    bio = biosimilar_intervals(con)
    flag = bio.groupby("npi")["vs_state"].agg(
        lambda s: "below_state" if (s == "below_state").any() else "above_state" if (s == "above_state").any()
        else "insufficient_data" if (s == "insufficient_data").all() else "not_distinguishable").rename("biosimilar_vs_state")
    sc = kp.merge(flag, on="npi", how="left")
    sc["biosimilar_vs_state"] = sc["biosimilar_vs_state"].fillna("no_multisource_infusions")
    keep = ["npi", "provider_type", "state_abbr", "county_fips", "benes", "allowed_per_bene", "allowed_per_bene_risk_adj",
            "services_per_bene", "drug_share", "infusion_share", "bills_chair_infusions", "allowed_per_bene_pctile",
            "allowed_per_bene_risk_adj_pctile", "services_per_bene_pctile", "drug_share_pctile",
            "infusion_share_pctile", "biosimilar_vs_state", "risk"]
    sc[keep].sort_values("npi").round(4).to_csv(EXPORTS / "fact_provider_scorecard.csv", index=False)
    bio.sort_values(["npi", "molecule"]).round(4).to_csv(EXPORTS / "fact_provider_biosimilar.csv", index=False)
    mkt = market_biosimilar_share(con)
    mkt.round(4).to_csv(EXPORTS / "fact_market_biosimilar_share.csv", index=False)
    infusers = sc[sc["bills_chair_infusions"]]
    summary = {
        "year": 2024,
        "n_providers_scored": int(len(sc)),
        "n_by_specialty": sc["provider_type"].value_counts().to_dict(),
        "biosimilar_molecules_assessed": sorted(bio["molecule"].unique().tolist()),
        "molecules_with_no_2024_biosimilar": sorted(set(MOLECULES) - set(bio["molecule"].unique())),
        "n_provider_molecule_pairs": int(len(bio)),
        "share_pairs_fully_observed": round(float(bio["fully_observed"].mean()), 4),
        "share_pairs_with_suppressed_codes": round(float((~bio["fully_observed"]).mean()), 4),
        "vs_state_counts_by_molecule": {m: g["vs_state"].value_counts().to_dict() for m, g in bio.groupby("molecule")},
        "provider_level_flags": sc["biosimilar_vs_state"].value_counts().to_dict(),
        "empirical_bayes": "not used: too few fully observed provider-molecule pairs to estimate a prior",
        "market_biosimilar_share_2024": {m: {r.geo: round(float(r.biosimilar_share), 4) for r in g.itertuples()}
                                         for m, g in mkt.groupby("molecule")},
        "median_by_specialty": sc.groupby("provider_type")[["allowed_per_bene", "allowed_per_bene_risk_adj",
                                                             "services_per_bene", "drug_share", "infusion_share"]]
        .median().round(4).to_dict(orient="index"),
        "infusing_providers": int(len(infusers)),
        "infusing_median_drug_share": round(float(infusers["drug_share"].median()), 4),
        "rheum_infusing_median_drug_share": round(float(
            infusers[infusers["provider_type"] == "Rheumatology"]["drug_share"].median()), 4),
    }
    (OUTPUTS / "benchmark.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("n_providers_scored", "biosimilar_molecules_assessed", "n_provider_molecule_pairs",
                                              "share_pairs_fully_observed", "vs_state_counts_by_molecule", "provider_level_flags")}, indent=1))


if __name__ == "__main__":
    main()
