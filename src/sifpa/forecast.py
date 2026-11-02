"""Module 3a: forecasts with a validation window for model choice and an untouched test window (ADR 0004).

  A. Quarterly ASP (implied, by ASP basis quarter) per HCPCS, horizons 1-6.
     The plan needs ASP(t-2) to price 2027 payments (h=1-4) and ASP(t) to cost 2027 purchases (h=3-6).
     Models: naive, seasonal naive (lag 4), drift (log), damped ETS (log).
     Guard: the first 2 quarters of a new code are dropped (launch pricing is WAC-based); a code with
     < 12 clean quarters, or a > 50% quarter move in the last 8, is held flat and flagged, not modelled.
  B. Annual national in-office Medicare FFS volume and allowed $ per molecule, 2013-2024, horizons 1-3.
     Volume and spend are scored separately; chair infusions and injections are reported apart.

  Model choice per series uses the VALIDATION window only; accuracy is reported on the TEST window
  (later origins whose targets never touch validation). Diebold-Mariano (HLN-corrected) compares the
  selected model with naive per horizon. 80% intervals are conformal quantiles of validation log
  errors per horizon; their coverage is measured on the test window.

`make forecast` -> outputs/forecast.json, outputs/price_path.csv, outputs/forecasts_annual_volume.csv,
                   outputs/forecast_backtest.csv, outputs/forecast_external_2025.csv
"""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from sifpa import engine as E
from sifpa.paths import OUTPUTS

warnings.filterwarnings("ignore")  # statsmodels convergence chatter on short series

H_Q, H_A = 6, 3
Q_VALID_LAST_TARGET, Q_TEST_FIRST_ORIGIN = "2023Q4", "2024Q1"
A_VALID_LAST_TARGET, A_TEST_FIRST_ORIGIN = 2020, 2021


# ---------- models: history -> h point forecasts ----------
def naive(y: np.ndarray, h: int, season: int = 4) -> np.ndarray:
    return np.repeat(y[-1], h)


def seasonal_naive(y: np.ndarray, h: int, season: int = 4) -> np.ndarray:
    return np.array([y[-season + (i % season)] for i in range(h)])


def drift(y: np.ndarray, h: int, season: int = 4) -> np.ndarray:
    """Random walk with drift on logs: average log growth continues (geometric drift)."""
    ly = np.log(y)
    slope = (ly[-1] - ly[0]) / (len(ly) - 1)
    return np.exp(ly[-1] + slope * np.arange(1, h + 1))


def ets_damped(y: np.ndarray, h: int, season: int = 4) -> np.ndarray:
    """Holt's linear trend with damping on logs; falls back to drift when the series is too short."""
    if len(y) < 5:
        return drift(y, h)
    fit = ExponentialSmoothing(np.log(y), trend="add", damped_trend=True, initialization_method="estimated").fit()
    return np.exp(fit.forecast(h))


QUARTERLY_MODELS = {"naive": naive, "seasonal_naive": seasonal_naive, "drift": drift, "ets_damped": ets_damped}
ANNUAL_MODELS = {"naive": naive, "drift": drift, "ets_damped": ets_damped}


def backtest(series: pd.Series, models: dict, horizons: int, first_origin: int, season: int) -> pd.DataFrame:
    """Rolling origin: train on y[:o+1], forecast o+1..o+h. Every model sees only past data."""
    y, labels, rows = series.to_numpy(dtype=float), list(series.index), []
    for o in range(first_origin, len(y) - 1):
        train = y[: o + 1]
        scale = np.mean(np.abs(np.diff(train))) if len(train) > 1 else np.nan
        h = min(horizons, len(y) - 1 - o)
        for name, fn in models.items():
            if name == "seasonal_naive" and len(train) < season:
                continue
            pred = fn(train, h, season)
            for k in range(h):
                actual = y[o + 1 + k]
                rows.append({"origin": labels[o], "target": labels[o + 1 + k], "h": k + 1, "model": name,
                             "actual": actual, "forecast": float(pred[k]), "ape": abs(pred[k] - actual) / actual,
                             "scaled_err": abs(pred[k] - actual) / scale if scale else np.nan,
                             "log_err": float(np.log(actual / pred[k]))})
    return pd.DataFrame(rows)


def dm_test(e_model: np.ndarray, e_base: np.ndarray, h: int) -> dict:
    """Diebold-Mariano on absolute-error loss with the Harvey-Leybourne-Newbold small-sample correction.
    Negative statistic = selected model has lower loss than the baseline."""
    d = np.abs(e_model) - np.abs(e_base)
    n = len(d)
    if n < 8:
        return {"n": n, "dm": None, "p_value": None}
    dbar = d.mean()
    gamma = [np.mean((d[k:] - dbar) * (d[: n - k] - dbar)) for k in range(h)]
    var = (gamma[0] + 2 * sum(gamma[1:])) / n
    if var <= 0:
        return {"n": n, "dm": None, "p_value": None}
    hln = dbar / np.sqrt(var) * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    return {"n": n, "dm": round(float(hln), 3), "p_value": round(float(2 * stats.t.sf(abs(hln), n - 1)), 4)}


def _coverage(errors: pd.DataFrame, q: pd.DataFrame) -> pd.DataFrame:
    e = errors.join(q, on="h")
    e["inside"] = e["log_err"].between(e["q10"], e["q90"])
    return e


def _quantiles(errors: pd.DataFrame) -> pd.DataFrame:
    return errors.groupby("h")["log_err"].quantile([0.1, 0.9]).unstack().rename(columns={0.1: "q10", 0.9: "q90"})


def evaluate(bt: pd.DataFrame, valid: pd.Series, test: pd.Series, select_on: str):
    """Select per series on validation; score on test; DM of selected vs naive; then apply the decision
    rule fixed in ADR 0004: keep the selected models only if they beat naive on test MAPE AND are not
    significantly worse (DM p < 0.05) at any horizon, else use naive everywhere.
    Returns (summary, plan quantiles per horizon, final model per series)."""
    v, t = bt[valid], bt[test]
    sel = v.groupby(["series", "model"])[select_on].mean().reset_index()
    chosen = sel.loc[sel.groupby("series")[select_on].idxmin()].set_index("series")["model"]
    t_sel = t[t["model"] == t["series"].map(chosen)]
    t_naive = t[t["model"] == "naive"]
    dm = {}
    for h, g in t_sel.groupby("h"):
        base = t_naive[t_naive["h"] == h].set_index(["series", "origin"])["log_err"]
        g2 = g.set_index(["series", "origin"])["log_err"]
        idx = sorted(g2.index.intersection(base.index), key=lambda k: (k[1], k[0]))  # time order
        dm[int(h)] = dm_test(g2.loc[idx].to_numpy(), base.loc[idx].to_numpy(), int(h))
    worse = any(d["p_value"] is not None and d["p_value"] < 0.05 and d["dm"] > 0 for d in dm.values())
    keep_selected = (t_sel["ape"].mean() < t_naive["ape"].mean()) and not worse
    final = chosen if keep_selected else chosen.map(lambda _m: "naive")
    v_fin = v[v["model"] == v["series"].map(final)]
    t_fin = t[t["model"] == t["series"].map(final)]
    cov = _coverage(t_fin, _quantiles(v_fin))  # honest: calibrated on validation, scored on test
    q_plan = _quantiles(pd.concat([v_fin, t_fin]))  # the 2027 plan uses every past error
    summary = {
        "test_mape_by_model": t.groupby("model")["ape"].mean().round(4).to_dict(),
        "test_mape_selected": round(float(t_sel["ape"].mean()), 4),
        "test_mape_naive": round(float(t_naive["ape"].mean()), 4),
        "test_mape_by_horizon": {"selected": t_sel.groupby("h")["ape"].mean().round(4).to_dict(),
                                 "naive": t_naive.groupby("h")["ape"].mean().round(4).to_dict()},
        "validation_mape_by_model": v.groupby("model")["ape"].mean().round(4).to_dict(),
        "selected_model_counts": chosen.value_counts().to_dict(),
        "dm_selected_vs_naive_by_h": dm,
        "decision": "selected models" if keep_selected else "naive (selected models did not beat naive on test)",
        "pi80_test_coverage_by_h": cov.groupby("h")["inside"].mean().round(4).to_dict(),
        "pi80_test_coverage_overall": round(float(cov["inside"].mean()), 4),
        "n_test_errors": int(len(t_fin)),
    }
    return summary, q_plan, final


# ---------- A. quarterly ASP price path ----------
def quarter_add(q: str, k: int) -> str:
    y, n = int(q[:4]), int(q[-1]) - 1 + k
    return f"{y + n // 4}Q{n % 4 + 1}"


def price_series(con) -> pd.DataFrame:
    """Implied ASP indexed by the ASP *basis* quarter (= payment quarter - 2). Rows priced by a non-ASP
    rule ("lesser of" WAC, AMP) carry PL / 1.06 and are flagged asp_estimated."""
    df = con.sql("""
        select f.hcpcs, d.molecule, d.product_type, f.payment_quarter,
               coalesce(f.asp_basis, f.payment_limit / (1 + f.addon_pct)) as asp,
               f.asp_basis is null as asp_estimated, f.flag_lesser_of
        from marts.fct_asp_quarter f join marts.dim_drug d using (hcpcs) order by 1, f.quarter_start
    """).df()
    df["basis_quarter"] = df["payment_quarter"].map(lambda q: quarter_add(q, -2))
    return df


def run_quarterly(con) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = price_series(con)
    bts, guards, clean = [], {}, {}
    for code, g in df.groupby("hcpcs"):
        g = g.iloc[2:] if g["payment_quarter"].min() > "2017Q1" else g  # drop WAC-priced launch quarters
        clean[code] = g
        s = g.set_index("basis_quarter")["asp"]
        recent = s.iloc[-9:].pct_change().abs().max() if len(s) > 1 else 0.0
        if len(s) < 12 or s.isna().any():
            guards[code] = "held_short_history"
        elif recent > 0.5:
            guards[code] = "held_volatile"
        else:
            bt = backtest(s, QUARTERLY_MODELS, H_Q, first_origin=11, season=4)
            bts.append(bt.assign(series=code))
    bt = pd.concat(bts, ignore_index=True)
    summary, q, chosen = evaluate(bt, bt["target"] <= Q_VALID_LAST_TARGET, bt["origin"] >= Q_TEST_FIRST_ORIGIN, "ape")
    lo_wide, hi_wide = np.exp(q["q10"].min()), np.exp(q["q90"].max())  # q = plan quantiles (all errors)
    for code in df["hcpcs"].unique():  # history too short to reach the validation window
        if code not in chosen.index:
            guards.setdefault(code, "held_no_validation_window")
    paths = []
    for code, g in df.groupby("hcpcs"):
        g = g.dropna(subset=["asp"])
        if g.empty:
            continue
        modelled = code in chosen.index
        y = (clean[code] if modelled else g)["asp"].to_numpy(dtype=float)
        model = chosen[code] if modelled else "held"
        pred = QUARTERLY_MODELS[model](y, H_Q, 4) if modelled else naive(y, H_Q)
        last = g["basis_quarter"].iloc[-1]
        paths.append({"hcpcs": code, "basis_quarter": last, "h": 0, "asp": y[-1], "lo80": y[-1], "hi80": y[-1],
                      "model": "actual", "guard": guards.get(code, "")})
        for k in range(H_Q):
            # held codes get the widest band seen at any horizon: honest about not modelling them
            lo, hi = (np.exp(q.loc[k + 1, "q10"]), np.exp(q.loc[k + 1, "q90"])) if modelled else (lo_wide, hi_wide)
            paths.append({"hcpcs": code, "basis_quarter": quarter_add(last, k + 1), "h": k + 1, "asp": pred[k],
                          "lo80": pred[k] * lo, "hi80": pred[k] * hi, "model": model, "guard": guards.get(code, "")})
    summary.update({"n_series_modelled": int(bt["series"].nunique()), "n_held": len(guards), "held": guards,
                    "valid_last_target": Q_VALID_LAST_TARGET, "test_first_origin": Q_TEST_FIRST_ORIGIN})
    return bt.assign(problem="quarterly_asp"), pd.DataFrame(paths), summary


# ---------- B. annual volume / spend ----------
def annual_series(con) -> pd.DataFrame:
    return con.sql("""
        select d.molecule,
               case when d.admin_family in ('mab_infusion', 'iv_infusion') then 'chair' else 'injection' end as kind,
               n.year, sum(n.bene_day_services) as administrations, sum(n.allowed_amt) as allowed
        from marts.fct_national_drug_year n join marts.dim_drug d using (hcpcs)
        where n.place_of_service = 'O' and d.admin_family <> 'procedure'
        group by 1, 2, 3 order by 1, 3
    """).df()


def run_annual(con) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = annual_series(con)
    span = df.groupby("molecule")["year"].agg(["min", "count"])
    keep = span[(span["min"] <= 2014) & (span["count"] >= 11)].index
    bts = []
    for mol in keep:
        g = df[df["molecule"] == mol].set_index("year")
        first = int(np.where(g.index == 2016)[0][0])
        for metric in ("administrations", "allowed"):
            bt = backtest(g[metric], ANNUAL_MODELS, H_A, first_origin=first, season=1)
            bts.append(bt.assign(series=f"{mol}|{metric}", metric=metric))
    bt = pd.concat(bts, ignore_index=True)
    summary, finals = {}, []
    for metric in ("administrations", "allowed"):
        b = bt[bt["metric"] == metric]
        s, q, chosen = evaluate(b, b["target"] <= A_VALID_LAST_TARGET, b["origin"] >= A_TEST_FIRST_ORIGIN, "scaled_err")
        summary[metric] = s
        for series, model in chosen.items():
            mol = series.split("|")[0]
            y = df[df["molecule"] == mol].set_index("year")[metric].to_numpy(dtype=float)
            pred = ANNUAL_MODELS[model](y, H_A, 1)
            for k, yr in enumerate((2025, 2026, 2027)):
                finals.append({"molecule": mol, "metric": metric, "year": yr, "model": model, "forecast": pred[k],
                               "lo80": pred[k] * np.exp(q.loc[k + 1, "q10"]),
                               "hi80": pred[k] * np.exp(q.loc[k + 1, "q90"])})
    summary.update({"n_molecules": int(len(keep)), "valid_last_target": A_VALID_LAST_TARGET,
                    "test_first_origin": A_TEST_FIRST_ORIGIN})
    return bt.assign(problem="annual"), pd.DataFrame(finals), summary


def external_2025(con) -> dict:
    """2025 all-settings Part B spend (never used in fitting) vs forecasts fit on the 2020-2024 file."""
    df = con.sql("""
        select d.molecule, s.year, sum(s.total_spending) as spend
        from marts.fct_partb_spending s join marts.dim_drug d using (hcpcs)
        where d.admin_family <> 'procedure' group by 1, 2 order by 1, 2
    """).df()
    rows = []
    for mol, g in df.groupby("molecule"):
        hist = g[g["year"] <= 2024]["spend"].to_numpy(dtype=float)
        if len(hist) < 5 or 2025 not in set(g["year"]):
            continue
        actual = float(g[g["year"] == 2025]["spend"].iloc[0])
        row = {"molecule": mol, "actual_2025": actual}
        for name, fn in ANNUAL_MODELS.items():
            row[f"{name}_2025"] = float(fn(hist, 1, 1)[0])
            row[f"{name}_ape"] = abs(row[f"{name}_2025"] - actual) / actual
        rows.append(row)
    t = pd.DataFrame(rows)
    t.round(4).to_csv(OUTPUTS / "forecast_external_2025.csv", index=False)
    w = t["actual_2025"] / t["actual_2025"].sum()
    return {"n_molecules": int(len(t)),
            "mape_2025": {m: round(float(t[f"{m}_ape"].mean()), 4) for m in ANNUAL_MODELS},
            "spend_weighted_ape_2025": {m: round(float((t[f"{m}_ape"] * w).sum()), 4) for m in ANNUAL_MODELS},
            "note": "Different series from the backtest: all-settings Part B spend (office + hospital outpatient)."}


def main() -> None:
    con = E.connect()
    bt_q, path, sum_q = run_quarterly(con)
    bt_a, fc_a, sum_a = run_annual(con)
    ext = external_2025(con)
    pd.concat([bt_q, bt_a]).round(6).to_csv(OUTPUTS / "forecast_backtest.csv", index=False)
    path.round(6).to_csv(OUTPUTS / "price_path.csv", index=False)
    fc_a.round(4).to_csv(OUTPUTS / "forecasts_annual_volume.csv", index=False)
    tot = annual_series(con).groupby(["kind", "year"])["administrations"].sum().unstack(0)
    out = {"quarterly_asp": sum_q, "annual": sum_a, "external_2025": ext,
           "national_inoffice_admins_2024": {k: round(float(tot.loc[2024, k])) for k in tot.columns},
           "national_inoffice_admin_cagr_2019_2024": {
               k: round(float((tot.loc[2024, k] / tot.loc[2019, k]) ** 0.2 - 1), 4) for k in tot.columns}}
    (OUTPUTS / "forecast.json").write_text(json.dumps(out, indent=2, default=float) + "\n")
    print(json.dumps({
        "q": {k: sum_q[k] for k in ("test_mape_by_model", "test_mape_selected", "selected_model_counts",
                                    "pi80_test_coverage_by_h", "dm_selected_vs_naive_by_h", "n_held")},
        "a_vol": {k: sum_a["administrations"][k] for k in ("test_mape_by_model", "test_mape_selected",
                                                            "pi80_test_coverage_by_h", "dm_selected_vs_naive_by_h")},
        "a_spend": {k: sum_a["allowed"][k] for k in ("test_mape_by_model", "test_mape_selected",
                                                      "pi80_test_coverage_overall")},
        "ext": ext, "nat": out["national_inoffice_admin_cagr_2019_2024"]}, indent=1, default=float))


if __name__ == "__main__":
    main()
