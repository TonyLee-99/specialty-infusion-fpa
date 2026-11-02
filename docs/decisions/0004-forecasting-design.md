# 0004. Forecasting: what is forecastable with public data, and how it is scored

Date: 2026-11-02. Status: accepted.

## Context
The brief asks for drug volume and spend forecasts, backtested with rolling origins against naive and
seasonal-naive baselines, with prediction intervals. Public Medicare utilization is **annual**
(2013-2024 by HCPCS). The quarterly Part B spending file has no history (ADR 0002). The only long
**quarterly** public series is the ASP payment limit (2017Q1-2026Q4).

## Decision
Two forecast problems, each scored against honest baselines:

1. **Annual in-office volume and allowed spend per molecule** (national Medicare FFS, place of service =
   office, 2013-2024, from "by Geography and Service").
   - Models: naive (last value), drift (random walk with drift), damped-trend ETS on log values.
   - Rolling origin: train through year T, forecast T+1 and T+2, for T = 2017..2023.
   - Metrics: MAPE and MASE (scaled by in-sample naive MAE). **There is no seasonal-naive baseline on
     annual data, because annual data has no seasonality. Saying so is more honest than inventing one.**
   - 2020 (COVID) stays in. Removing it would flatter the models.
2. **Quarterly ASP payment limit per HCPCS** (40 quarters).
   - Models: naive, seasonal naive (same quarter last year), drift on log, damped ETS on log.
   - Rolling origin, horizons h = 1..4 quarters. The h=1 forecast is partly known in practice because
     of the 2-quarter lag. That is stated, not hidden.
3. **Prediction intervals** = empirical quantiles (10/90) of backtest errors by horizon and model,
   applied to the final forecast. This is conformal-style and assumes nothing about the error
   distribution.
4. **Model selection rule, fixed before results**: use the model with the lowest backtest MASE
   (annual) or MAPE (quarterly) per series. If no model beats naive, the plan uses naive, and the README
   says so.
5. **External check**: the 2025 forecast of all-settings Part B spend by molecule is compared with the
   2025 actual from the Quarterly Part B Spending file. That year was never used in fitting.

## Consequences
Spend for the 2027 plan = volume forecast x price forecast, with intervals from both. Misses are
reported as measured.

## Known optimism (stated, not fixed)
Picking the best model per series on the same backtest that reports its error flatters the winner. The
pooled model-level MAPE/MASE in `outputs/forecast.json` is the unbiased comparison. The per-series
"best beats naive" share is an upper bound.

## Revision 1: validation / test split and the decision rule
- Model choice per series uses a **validation window** (targets up to 2023Q4 for quarterly ASP, up to
  2020 for annual volume/spend). Accuracy is reported on a **test window** (origins from 2024Q1 / 2021)
  whose targets never touch validation.
- **Decision rule (fixed before looking at test results):** keep the selected models only if they beat
  naive on test MAPE AND are not significantly worse (Diebold-Mariano with HLN correction, p < 0.05) at
  any horizon; otherwise use naive everywhere. Result: quarterly ASP test MAPE is 6.6% naive vs 6.4%
  selected, but DM shows the selected models significantly worse on absolute log error at every horizon
  (p 0.004-0.023). Annual volume: 16.4% naive vs 18.3% selected. Spend: 20.2% vs 28.8%. **The plan uses
  naive everywhere**, so 2027 prices and volumes are held at the latest actuals.
- **Intervals** are conformal: 10/90% quantiles of validation log errors per horizon. Test-window
  coverage of the naive bands is 78-89% for quarterly ASP (h = 1-6), 77-82% for volume, and 64-68% for
  spend. The spend miss is reported, not tuned away. The 2027 plan intervals use all past errors.
- Volume (11 molecules) and spend are scored separately. National in-office volume is split into chair
  infusions (1.09M in 2024, +4.6%/yr since 2019) and injections.
- The volume forecast is wired into the plan as a demand-growth factor per molecule. With naive chosen,
  the factor is 1.0.
