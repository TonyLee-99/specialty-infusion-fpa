"""Module 3a: forecasts with rolling-origin backtests against baselines (ADR 0004).

  A. Annual national in-office Medicare FFS administrations and allowed $ per molecule, 2013-2024.
     Models: naive, drift, damped-trend ETS (log). No seasonal naive: annual data has no seasonality.
  B. Quarterly ASP payment limit per HCPCS, 2017Q1-2026Q4.
     Models: naive, seasonal naive (lag 4), drift (log), damped-trend ETS (log).
  Prediction intervals = empirical 10/90% quantiles of backtest log errors by model x horizon,
  calibrated on early origins and coverage-tested on later origins (honest, not in-sample).
  External check: 2025 all-settings Part B spend vs the 2025 actual (never used in fitting).

`make forecast` -> outputs/forecast_backtest.csv, outputs/forecast.json, outputs/forecasts_*.csv
"""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from sifpa import engine as E
from sifpa.paths import OUTPUTS

warnings.filterwarnings("ignore")  # statsmodels convergence chatter on short series


# ---------- models: each takes a 1-d history and a horizon, returns h point forecasts ----------
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


ANNUAL_MODELS = {"naive": naive, "drift": drift, "ets_damped": ets_damped}
QUARTERLY_MODELS = {"naive": naive, "seasonal_naive": seasonal_naive, "drift": drift, "ets_damped": ets_damped}


def backtest(series: pd.Series, models: dict, horizons: int, first_origin: int, season: int) -> pd.DataFrame:
    """Rolling origin: for each origin index o (train = y[:o+1]) forecast o+1..o+h; record errors."""
    y = series.to_numpy(dtype=float)
    labels = list(series.index)
    rows = []
    for o in range(first_origin, len(y) - 1):
        train = y[: o + 1]
        # in-sample naive MAE (one-step) scales MASE
        scale = np.mean(np.abs(np.diff(train))) if len(train) > 1 else np.nan
        h = min(horizons, len(y) - 1 - o)
        for name, fn in models.items():
            pred = fn(train, h, season)
            for k in range(h):
                actual = y[o + 1 + k]
                rows.append({"origin": labels[o], "target": labels[o + 1 + k], "h": k + 1, "model": name,
                             "actual": actual, "forecast": float(pred[k]),
                             "ape": abs(pred[k] - actual) / actual, "scaled_err": abs(pred[k] - actual) / scale,
                             "log_err": float(np.log(actual / pred[k]))})
    return pd.DataFrame(rows)


def summarise(bt: pd.DataFrame, key: str) -> pd.DataFrame:
    s = bt.groupby([key, "model"]).agg(mape=("ape", "mean"), mase=("scaled_err", "mean"), n=("ape", "size")).reset_index()
    return s


def interval_quantiles(bt: pd.DataFrame, calib_mask: pd.Series) -> pd.DataFrame:
    """10/90% quantiles of log errors per model x horizon from the calibration origins."""
    return bt[calib_mask].groupby(["model", "h"])["log_err"].quantile([0.1, 0.9]).unstack().rename(
        columns={0.1: "q10", 0.9: "q90"}).reset_index()


def coverage(bt: pd.DataFrame, q: pd.DataFrame, eval_mask: pd.Series) -> pd.DataFrame:
    e = bt[eval_mask].merge(q, on=["model", "h"])
    e["inside"] = (e["log_err"] >= e["q10"]) & (e["log_err"] <= e["q90"])
    return e.groupby("model")["inside"].agg(["mean", "size"]).reset_index().rename(
        columns={"mean": "coverage_80", "size": "n_eval"})


# ---------- A. annual volume / spend ----------
def annual_series(con) -> pd.DataFrame:
    return con.sql("""
        select d.molecule, n.year, sum(n.bene_day_services) as administrations, sum(n.allowed_amt) as allowed
        from marts.fct_national_drug_year n join marts.dim_drug d using (hcpcs)
        where n.place_of_service = 'O' and d.admin_family <> 'procedure'
        group by 1, 2 order by 1, 2
    """).df()


def run_annual(con) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = annual_series(con)
    full = df.groupby("molecule")["year"].agg(["min", "count"])
    keep = full[(full["min"] <= 2015) & (full["count"] >= 10)].index  # long enough to backtest 2017+
    bts, finals = [], []
    for mol in keep:
        g = df[df["molecule"] == mol].set_index("year")
        for metric in ("administrations", "allowed"):
            s = g[metric]
            first = int(np.where(s.index == 2017)[0][0])
            bt = backtest(s, ANNUAL_MODELS, horizons=2, first_origin=first, season=1)
            bt["series"], bt["metric"] = f"{mol}|{metric}", metric
            bts.append(bt)
    bt = pd.concat(bts, ignore_index=True)
    calib = bt["origin"] <= 2020
    q = interval_quantiles(bt, calib)
    cov = coverage(bt, q, ~calib)
    per_series = summarise(bt, "series")
    best = per_series.loc[per_series.groupby("series")["mase"].idxmin()].set_index("series")
    for series, row in best.iterrows():
        mol, metric = series.split("|")
        y = df[df["molecule"] == mol].set_index("year")[metric].to_numpy(dtype=float)
        pred = ANNUAL_MODELS[row["model"]](y, 3, 1)
        for k, yr in enumerate((2025, 2026, 2027)):
            qq = q[(q["model"] == row["model"]) & (q["h"] == min(k + 1, 2))].iloc[0]
            finals.append({"series": series, "molecule": mol, "metric": metric, "year": yr, "model": row["model"],
                           "forecast": pred[k], "lo80": pred[k] * np.exp(qq["q10"]), "hi80": pred[k] * np.exp(qq["q90"])})
    naive_mase = per_series[per_series["model"] == "naive"].set_index("series")["mase"]
    summary = {
        "n_series": int(per_series["series"].nunique()),
        "origins": sorted(bt["origin"].unique().tolist()),
        "mape_by_model": summarise(bt.assign(all="all"), "all").set_index("model")["mape"].round(4).to_dict(),
        "mase_by_model": summarise(bt.assign(all="all"), "all").set_index("model")["mase"].round(4).to_dict(),
        "share_series_best_beats_naive": round(float((best["mase"] < naive_mase.reindex(best.index)).mean()), 4),
        "pi80_coverage_eval": cov.round(4).to_dict(orient="records"),
    }
    return bt, pd.DataFrame(finals), summary


# ---------- B. quarterly ASP ----------
def run_quarterly(con) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = con.sql("""
        select f.hcpcs, d.molecule, f.payment_quarter, f.payment_limit
        from marts.fct_asp_quarter f join marts.dim_drug d using (hcpcs)
        where d.product_type in ('reference', 'single_source') order by 1, 3
    """).df()
    counts = df.groupby("hcpcs").size()
    keep = counts[counts == 40].index  # complete 2017Q1-2026Q4 history only
    bts, finals = [], []
    for code in keep:
        s = df[df["hcpcs"] == code].set_index("payment_quarter")["payment_limit"]
        bt = backtest(s, QUARTERLY_MODELS, horizons=4, first_origin=19, season=4)  # first origin 2021Q4
        bt["series"] = code
        bts.append(bt)
    bt = pd.concat(bts, ignore_index=True)
    calib = bt["origin"] <= "2023Q4"
    q = interval_quantiles(bt, calib)
    cov = coverage(bt, q, ~calib)
    per_series = summarise(bt, "series")
    best = per_series.loc[per_series.groupby("series")["mape"].idxmin()].set_index("series")
    for code, row in best.iterrows():
        y = df[df["hcpcs"] == code]["payment_limit"].to_numpy(dtype=float)
        pred = QUARTERLY_MODELS[row["model"]](y, 4, 4)
        for k, quarter in enumerate(("2027Q1", "2027Q2", "2027Q3", "2027Q4")):
            qq = q[(q["model"] == row["model"]) & (q["h"] == k + 1)].iloc[0]
            finals.append({"hcpcs": code, "quarter": quarter, "model": row["model"], "forecast": pred[k],
                           "lo80": pred[k] * np.exp(qq["q10"]), "hi80": pred[k] * np.exp(qq["q90"]),
                           "last_actual_2026Q4": y[-1]})
    naive_mape = per_series[per_series["model"] == "naive"].set_index("series")["mape"]
    snaive_mape = per_series[per_series["model"] == "seasonal_naive"].set_index("series")["mape"]
    overall = summarise(bt.assign(all="all"), "all").set_index("model")
    by_h = bt.groupby(["model", "h"])["ape"].mean().unstack().round(4)
    summary = {
        "n_series": int(len(keep)),
        "first_origin": "2021Q4", "last_origin": sorted(bt["origin"].unique())[-1],
        "mape_by_model": overall["mape"].round(4).to_dict(),
        "mape_by_model_and_horizon": {m: by_h.loc[m].to_dict() for m in by_h.index},
        "share_series_best_beats_naive": round(float((best["mape"] < naive_mape.reindex(best.index)).mean()), 4),
        "share_series_best_beats_seasonal_naive": round(float((best["mape"] < snaive_mape.reindex(best.index)).mean()), 4),
        "best_model_counts": best["model"].value_counts().to_dict(),
        "pi80_coverage_eval": cov.round(4).to_dict(orient="records"),
    }
    return bt, pd.DataFrame(finals), summary


# ---------- external check: 2025 all-settings Part B spend ----------
def external_2025(con) -> dict:
    df = con.sql("""
        select d.molecule, s.year, sum(s.total_spending) as spend, max(s.source) as source
        from marts.fct_partb_spending s join marts.dim_drug d using (hcpcs)
        where d.admin_family <> 'procedure'
        group by 1, 2 order by 1, 2
    """).df()
    rows = []
    for mol, g in df.groupby("molecule"):
        hist = g[g["year"] <= 2024].set_index("year")["spend"]
        if len(hist) < 5 or 2025 not in set(g["year"]):
            continue
        actual = float(g[g["year"] == 2025]["spend"].iloc[0])
        y = hist.to_numpy(dtype=float)
        row = {"molecule": mol, "actual_2025": actual}
        for name, fn in ANNUAL_MODELS.items():
            row[f"{name}_2025"] = float(fn(y, 1, 1)[0])
            row[f"{name}_ape"] = abs(row[f"{name}_2025"] - actual) / actual
        rows.append(row)
    t = pd.DataFrame(rows)
    t.round(4).to_csv(OUTPUTS / "forecast_external_2025.csv", index=False)
    return {"n_molecules": int(len(t)),
            "mape_2025": {m: round(float(t[f"{m}_ape"].mean()), 4) for m in ANNUAL_MODELS},
            "median_ape_2025": {m: round(float(t[f"{m}_ape"].median()), 4) for m in ANNUAL_MODELS},
            "note": "2025 actual from the Quarterly Part B Spending file (all settings); fit on 2020-2024 annual file."}


def main() -> None:
    con = E.connect()
    bt_a, fc_a, sum_a = run_annual(con)
    bt_q, fc_q, sum_q = run_quarterly(con)
    ext = external_2025(con)
    pd.concat([bt_a.assign(problem="annual_volume"), bt_q.assign(problem="quarterly_asp")]).round(6).to_csv(
        OUTPUTS / "forecast_backtest.csv", index=False)
    fc_a.round(4).to_csv(OUTPUTS / "forecasts_annual_volume.csv", index=False)
    fc_q.round(4).to_csv(OUTPUTS / "forecasts_quarterly_asp.csv", index=False)
    hist = annual_series(con)
    cagr = (hist[hist["year"].isin([2019, 2024])].pivot(index="molecule", columns="year", values="administrations")
            .dropna())
    total = hist.groupby("year")[["administrations", "allowed"]].sum()
    out = {"annual": sum_a, "quarterly_asp": sum_q, "external_2025": ext,
           "national_inoffice_administrations_2019": round(float(total.loc[2019, "administrations"])),
           "national_inoffice_administrations_2024": round(float(total.loc[2024, "administrations"])),
           "national_inoffice_allowed_2024": round(float(total.loc[2024, "allowed"])),
           "national_inoffice_admin_cagr_2019_2024": round(float(
               (total.loc[2024, "administrations"] / total.loc[2019, "administrations"]) ** (1 / 5) - 1), 4),
           "molecules_growing_2019_2024": int((cagr[2024] > cagr[2019]).sum()),
           "molecules_compared_2019_2024": int(len(cagr))}
    (OUTPUTS / "forecast.json").write_text(json.dumps(out, indent=2, default=float) + "\n")
    print(json.dumps({k: out[k] for k in ("external_2025",)}, indent=1))
    print("annual", json.dumps({k: sum_a[k] for k in ("mape_by_model", "mase_by_model", "share_series_best_beats_naive", "pi80_coverage_eval")}))
    print("quarterly", json.dumps({k: sum_q[k] for k in ("mape_by_model", "share_series_best_beats_naive", "share_series_best_beats_seasonal_naive", "best_model_counts", "pi80_coverage_eval")}))


if __name__ == "__main__":
    main()
