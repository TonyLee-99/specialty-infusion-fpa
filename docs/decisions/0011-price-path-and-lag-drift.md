# 0011. 2027 price path in the base vs the lag-drift scenario

Date: 2026-11-02. Status: accepted.

## Context
The first revision put the 2-quarter lag into the engine but held prices flat, which cancelled it. The second removed
the test window from the model decision (ADR 0004), and the decision window now keeps the selected
models (mostly drift and damped ETS). The base path therefore rises gently, and the lag shows up in the
base.

## Decision
1. **Base** = the forecast path chosen by the decision-window rule. Payment is on the forecast ASP(t-2)
   and purchase at the forecast ASP(t).
2. **Lag-drift scenario** (sensitivity, not base) = each drug's own median lag spread over the last 8
   quarters persists, so purchase price = PL / (1 + median lag). It uses the repo's
   `outputs/lag_spread_by_drug.csv`. Drugs with fewer than 8 quarters keep the forecast path.
3. Why not the base: the lag-drift scenario backs today's price out of the last two years of price rises.
   That is a valid stress, but it is not a forecast, and on the test window both forecast families
   already under-forecast prices (+1.8% naive bias).

## Result
The lag-drift scenario changes operating margin by -$335K vs base. Ocrevus (-$130K), Vyepti (-$100K) and
Inflectra (-$96K) lead it. It is reported in the memo's risk section and in `outputs/scenarios.json`.
