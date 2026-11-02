"""`make scorecard`: static HTML scorecard mirroring the intended Power BI report pages.

Self-contained (inline SVG, no JS libraries, no network). Every number is read from outputs/*.json or
exports/*.csv. Hover: each mark carries an SVG <title> tooltip. Palette: validated reference palette
(dataviz skill, slots 1-4 adjacent-pair checked); text never wears series colors.
"""

from __future__ import annotations

import html
import json

import pandas as pd

from sifpa.paths import DOCS, EXPORTS, OUTPUTS

S1, S2, S3, S4 = "var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"


def J(name: str) -> dict:
    return json.loads((OUTPUTS / name).read_text())


def money(x: float, digits: int = 0) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e9:
        return f"{sign}${x / 1e9:.2f}B"
    if x >= 1e6:
        return f"{sign}${x / 1e6:.2f}M"
    if x >= 1e4:
        return f"{sign}${x / 1e3:.0f}K"
    return f"{sign}${x:,.{digits}f}"


def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def esc(s) -> str:
    return html.escape(str(s))


def tile(label: str, value: str, note: str = "") -> str:
    return (f'<div class="tile"><div class="tlabel">{esc(label)}</div><div class="tvalue">{esc(value)}</div>'
            f'<div class="tnote">{esc(note)}</div></div>')


def hbars(rows: list[tuple[str, list[float]]], series: list[tuple[str, str]], fmt, width=760, bar=12) -> str:
    """Horizontal grouped bars from a zero baseline (handles negatives). rows: (label, [v per series])."""
    label_w, pad = 200, 70
    vals = [v for _, vs in rows for v in vs]
    lo, hi = min(0.0, min(vals)), max(0.0, max(vals))
    span = (hi - lo) or 1.0
    neg_pad = 64 if lo < 0 else 0  # room for value labels left of negative bars
    plot_w = width - label_w - pad - neg_pad
    x = lambda v: label_w + neg_pad + (v - lo) / span * plot_w  # noqa: E731
    group_h = bar * len(series) + 2 * (len(series) - 1) + 12
    h = group_h * len(rows) + 8
    out = [f'<svg viewBox="0 0 {width} {h}" role="img" class="chart">',
           f'<line x1="{x(0):.1f}" x2="{x(0):.1f}" y1="0" y2="{h - 4}" class="axis"/>']
    for i, (label, vs) in enumerate(rows):
        y0 = i * group_h + 4
        out.append(f'<text x="{label_w - 8}" y="{y0 + group_h / 2 - 2:.1f}" class="lbl" text-anchor="end">{esc(label)}</text>')
        for j, (sname, color) in enumerate(series):
            v = vs[j]
            y = y0 + j * (bar + 2)
            x0, x1 = sorted((x(0), x(v)))
            out.append(f'<rect x="{x0:.1f}" y="{y}" width="{max(x1 - x0, 1):.1f}" height="{bar}" rx="3" fill="{color}">'
                       f'<title>{esc(label)} | {esc(sname)}: {esc(fmt(v))}</title></rect>')
            tx = x1 + 4 if v >= 0 else x0 - 4
            out.append(f'<text x="{tx:.1f}" y="{y + bar - 2}" class="val" text-anchor="{"start" if v >= 0 else "end"}">{esc(fmt(v))}</text>')
    out.append("</svg>")
    legend = "".join(f'<span class="key"><i style="background:{c}"></i>{esc(n)}</span>' for n, c in series)
    return f'<div class="legend">{legend}</div>' + "".join(out) if len(series) > 1 else "".join(out)


def lines(series: list[tuple[str, str, list[tuple[str, float]]]], fmt, width=760, height=280) -> str:
    """Multi-series line chart over shared x labels (quarters); direct labels at line ends."""
    xs = sorted({x for _, _, pts in series for x, _ in pts})
    ys = [v for _, _, pts in series for _, v in pts]
    lo, hi = 0.0, max(ys) * 1.08
    left, right, top, bottom = 50, 150, 10, 30
    px = lambda xv: left + xs.index(xv) / (len(xs) - 1) * (width - left - right)  # noqa: E731
    py = lambda v: top + (1 - (v - lo) / (hi - lo)) * (height - top - bottom)  # noqa: E731
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        out.append(f'<line x1="{left}" x2="{width - right}" y1="{py(v):.1f}" y2="{py(v):.1f}" class="grid"/>'
                   f'<text x="{left - 6}" y="{py(v) + 4:.1f}" class="tick" text-anchor="end">{esc(fmt(v))}</text>')
    for xv in xs[:: max(1, len(xs) // 8)]:
        out.append(f'<text x="{px(xv):.1f}" y="{height - 10}" class="tick" text-anchor="middle">{esc(xv)}</text>')
    ends = []
    for name, color, pts in series:
        d = " ".join(f"{'M' if i == 0 else 'L'}{px(x):.1f},{py(v):.1f}" for i, (x, v) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, v in pts:
            out.append(f'<circle cx="{px(x):.1f}" cy="{py(v):.1f}" r="6" fill="transparent">'
                       f'<title>{esc(name)} {esc(x)}: {esc(fmt(v))}</title></circle>')
        ends.append([py(pts[-1][1]), f"{name} {fmt(pts[-1][1])}"])
    ends.sort()
    for i in range(1, len(ends)):  # keep end labels in value order, at least 13px apart
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 13)
    for ly, text in ends:
        out.append(f'<text x="{width - right + 8}" y="{ly + 4:.1f}" class="lbl">{esc(text)}</text>')
    out.append("</svg>")
    legend = "".join(f'<span class="key"><i style="background:{c}"></i>{esc(n)}</span>' for n, c, _ in series)
    return f'<div class="legend">{legend}</div>' + "".join(out)


def table(df: pd.DataFrame) -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in df.columns)
    body = "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in r) + "</tr>" for r in df.itertuples(index=False))
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def build() -> str:
    m, sc, fc, bm, mk, kp = (J(n) for n in ("margin.json", "scenarios.json", "forecast.json", "benchmark.json",
                                             "market.json", "kpis.json"))
    rcm, var, tor = J("rcm_kpis_SYNTHETIC.json"), J("variance_pack_SYNTHETIC.json"), J("tornado.json")
    s = sc["scenarios"]
    base = s["base"]
    op = base["operating_margin"]

    # ---- page 1: executive (2027 basis throughout) ----
    p1 = "".join([
        tile("CY2027 operating margin (illustrative 12-chair suite)", money(op),
             f'{base["administrations"]:,} infusions/yr, {pct(base["utilization"], 0)} of chair capacity'),
        tile("Contribution per infusion: Medicare FFS", money(base["contribution_per_admin_medicare_ffs"], 0),
             f'drug margin {pct(m["medicare_drug_margin_pct_of_drug_revenue"])} of Medicare drug revenue'),
        tile("Contribution per infusion: commercial (assumed contract)", money(base["contribution_per_admin_commercial"], 0),
             f'commercial = {pct(base["commercial_share_of_contribution"], 0)} of contribution'),
        tile("2028 policy run-rate vs base", money(s["policy_2028"]["operating_margin"] - op),
             f'white bagging {money(sc["policy_2028_bridge"]["white_bagging_net_of_ivs"])}; MFP {money(sc["policy_2028_bridge"]["mfp"])}'),
        tile("Biosimilars on listed products (Inflectra, Truxima)", money(s["biosimilar_listed"]["operating_margin"] - op),
             f'best product per payer: up to {money(s["biosimilar_best"]["operating_margin"] - op)}'),
        tile("Grow by patients, not chairs", money(sc["value_of_100_more_patients"]),
             f'per 100 more patients; one more chair today: {money(base["added_chair_value"])}/yr'),
    ])
    order = ["base", "biosimilar_listed", "biosimilar_best", "policy_2028"]
    p1 += '<h3>CY2027 operating margin by scenario</h3>' + hbars(
        [(k.replace("_", " "), [s[k]["operating_margin"]]) for k in order], [("Operating margin", S1)], money)
    bars = tor["bars"][:8]
    p1 += ('<h3>Tornado: change in operating margin, each assumption at its documented low / high</h3>'
           + hbars([(b["driver"].replace("_", " ")[:30], [b["at_low"] - tor["base"], b["at_high"] - tor["base"]]) for b in bars],
                   [("at low value", S2), ("at high value", S1)], money))

    # ---- page 2: pricing & margin ----
    asp = pd.read_csv(EXPORTS / "fact_asp_quarter.csv", dtype={"hcpcs": str})
    names = {"J1745": "Remicade J1745", "Q5103": "Inflectra Q5103", "Q5104": "Renflexis Q5104", "Q5121": "Avsola Q5121"}
    series = []
    for code, color in zip(names, (S1, S2, S3, S4), strict=True):
        g = asp[asp["hcpcs"] == code]
        series.append((names[code], color, list(zip(g["payment_quarter"], g["payment_limit"], strict=True))))
    p2 = '<h3>Infliximab: Medicare payment limit per 10 mg, by product (CMS ASP files, 2017Q1-2026Q4)</h3>'
    p2 += lines(series, lambda v: f"${v:,.0f}")
    cph = m["contribution_per_chair_hour"][:12]
    p2 += ('<h3>Contribution per chair-hour, drugs in the 2027 plan mix</h3>'
           + hbars([(f'{r["molecule"]} {r["hcpcs"]}', [r["medicare_ffs_per_chair_hour"], r["commercial_per_chair_hour"]]) for r in cph],
                   [("Medicare FFS", S1), ("Commercial (assumed)", S2)], money))
    dec = pd.read_csv(OUTPUTS / "biosimilar_decision.csv")
    best = dec[dec["best_for_payer"]][["molecule", "payer", "brand", "drug_margin_base", "decision_robust"]]
    best["drug_margin_base"] = best["drug_margin_base"].map(lambda x: f"${x:,.0f}")
    p2 += "<h3>Biosimilar decision: best product per payer (robust = survives the product's p10/p90 price swing)</h3>" + table(best)
    uw = m["underwater"]
    p2 += (f'<p class="note">Medicare collected payment below the current purchase price: {pct(uw["raw"]["share_drug_quarters"])} of '
           f'drug-quarters raw, {pct(uw["after_sequestration"]["share_drug_quarters"])} after sequestration, '
           f'{pct(uw["after_sequestration_and_coinsurance"]["share_drug_quarters"])} after sequestration and coinsurance '
           f'({pct(uw["after_sequestration_and_coinsurance"]["dollar_weighted_share"])} dollar-weighted).</p>')

    # ---- page 3: forecasts ----
    qa, av, al = fc["quarterly_asp"], fc["annual"]["administrations"], fc["annual"]["allowed"]
    models = ["naive", "seasonal_naive", "drift", "ets_damped"]
    p3 = (f'<h3>Quarterly ASP: test-window MAPE by model (origins from {qa["test_first_origin"]}, h = 1-6)</h3>'
          + hbars([(mm.replace("_", " "), [qa["test_mape_by_model_all_forecasts"][mm]]) for mm in models], [("MAPE", S1)], pct))
    dmq = qa["dm_per_series_h1"]
    p3 += table(pd.DataFrame([{"matched test forecasts": qa["test_matched_n"], "naive MAPE": pct(qa["test_mape_naive"]),
                               "selected MAPE": pct(qa["test_mape_selected"]), "series tested (DM, h=1)": dmq["n_series_tested"],
                               "selected significantly better": dmq["selected_significantly_better"],
                               "selected significantly worse": dmq["selected_significantly_worse"],
                               "80% band coverage": pct(qa["pi80_test_coverage_overall"])}]))
    p3 = p3.replace("<h3>Quarterly ASP: test-window MAPE by model", "<h3>Quarterly ASP: test-window MAPE by model (all forecasts)")
    p3 += f'<p class="note">Decision ({esc(qa["decision"])}) was made on a separate decision window, never on the test window.</p>'
    p3 += ("<h3>Annual national in-office series, test-window MAPE: volume and spend scored separately</h3>"
           + hbars([("volume: naive", [av["test_mape_naive"]]), ("volume: selected", [av["test_mape_selected"]]),
                    ("spend: naive", [al["test_mape_naive"]]), ("spend: selected", [al["test_mape_selected"]])], [("MAPE", S1)], pct))

    # ---- page 4: growth & benchmark ----
    top = pd.DataFrame(mk["market_top10"])
    p4 = (f'<h3>White space: top 10 of {mk["markets"]["n_eligible"]} eligible markets (share of {mk["n_weight_draws"]:,} random weightings in the top 10)</h3>'
          + hbars([(r.market[:30], [r.share_of_weightings_in_top10]) for r in top.itertuples()], [("share of weightings", S1)], pct))
    t = top[["rank", "market", "share_of_weightings_in_top10", "specialists_per_100k", "rheumatologists",
             "infusion_billers_per_100k", "hospital_heavy", "miles_to_columbus_site"]].copy()
    t["share_of_weightings_in_top10"] = t["share_of_weightings_in_top10"].map(pct)
    p4 += table(t)
    share = pd.read_csv(EXPORTS / "fact_market_biosimilar_share.csv")
    inf = share[share["molecule"] == "infliximab"].sort_values("biosimilar_share", ascending=False)
    p4 += ("<h3>Infliximab biosimilar share of in-office administrations, 2024 (unsuppressed geography totals)</h3>"
           + hbars([(r.geo, [r.biosimilar_share]) for r in inf.itertuples()], [("Biosimilar share", S1)], pct))
    p4 += (f'<p class="note">Provider level ({bm["n_providers_scored"]:,} clinicians): {pct(bm["share_pairs_fully_observed"], 0)} of '
           f'{bm["n_provider_molecule_pairs"]} provider-molecule pairs are fully observed after CMS suppression, so provider biosimilar '
           f'labels are interval-based and mostly "insufficient data".</p>')

    # ---- page 5: budget vs actual (SYNTHETIC) ----
    p6 = '<div class="synthetic">SYNTHETIC ACTUALS: method demo only. Budget = 2027 plan model.</div>'
    rows = var["by_site_ytd"]
    p6 += ("<h3>Contribution variance, months closed (SYNTHETIC actuals): volume / mix / rate by site</h3>"
           + hbars([(f'{r["site_id"]} {k}', [r[k]]) for r in rows for k in ("volume", "mix", "rate", "variance")],
                   [("contribution $", S1)], money))

    # ---- page 6: RCM SYNTHETIC ----
    p5 = '<div class="synthetic">SYNTHETIC DATA: method demo only. No business conclusion is drawn from this page.</div>'
    p5 += "".join([tile("Clean-claim rate (SYNTHETIC)", pct(rcm["clean_claim_rate"])),
                   tile("Initial denial rate (SYNTHETIC)", pct(rcm["denial_rate"])),
                   tile("Days in AR (SYNTHETIC)", f'{rcm["days_in_ar"]:.1f}'),
                   tile("Net collection rate (SYNTHETIC)", pct(rcm["net_collection_rate"]))])
    p5 += ("<h3>Initial denials by CARC group, share of first remits (SYNTHETIC)</h3>"
           + hbars(list((k, [v]) for k, v in rcm["denial_rate_by_carc_group"].items()), [("share", S3)], pct))

    sections = [("exec", "Executive summary (2027 basis)", p1), ("pricing", "Pricing, ASP lag and margin per infusion", p2),
                ("forecast", "Forecasts", p3), ("market", "Growth and benchmark", p4),
                ("variance", "Budget vs actual (SYNTHETIC actuals)", p6), ("rcm", "Revenue cycle (SYNTHETIC)", p5)]
    nav = "".join(f'<a href="#{i}">{esc(t)}</a>' for i, t, _ in sections)
    body = "".join(f'<section id="{i}"><h2>{esc(t)}</h2><div class="tiles">{c}</div></section>'
                   if i in ("exec", "rcm", "variance") else f'<section id="{i}"><h2>{esc(t)}</h2>{c}</section>' for i, t, c in sections)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Specialty infusion FP&amp;A scorecard</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>
:root {{ color-scheme: light; --bg:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --rule:#e4e3df;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; }}
@media (prefers-color-scheme: dark) {{ :root {{ color-scheme: dark; --bg:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7;
  --rule:#383835; --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; }} }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif; }}
header {{ padding:20px 32px 8px; border-bottom:1px solid var(--rule); }}
header h1 {{ margin:0 0 4px; font-size:22px; }} header p {{ margin:0; color:var(--ink2); }}
nav {{ padding:8px 32px; border-bottom:1px solid var(--rule); }} nav a {{ margin-right:18px; color:var(--ink); }}
section {{ padding:16px 32px 28px; max-width:1100px; }} h2 {{ font-size:18px; margin:8px 0 12px; }}
h3 {{ font-size:14px; margin:22px 0 6px; color:var(--ink); }}
.tiles {{ display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:12px; }}
.tiles h3, .tiles .legend, .tiles svg, .tiles .synthetic {{ grid-column:1 / -1; }}
.tile {{ border:1px solid var(--rule); border-radius:8px; padding:12px 14px; }}
.tlabel {{ color:var(--ink2); font-size:12px; }} .tvalue {{ font-size:26px; font-weight:600; margin:4px 0; }}
.tnote {{ color:var(--ink2); font-size:12px; }}
.chart {{ width:100%; max-width:820px; height:auto; display:block; }}
.chart .lbl {{ font-size:12px; fill:var(--ink); }} .chart .val, .chart .tick {{ font-size:11px; fill:var(--ink2); }}
.chart .axis {{ stroke:var(--ink2); stroke-width:1; }} .chart .grid {{ stroke:var(--rule); stroke-width:1; }}
.legend {{ font-size:12px; color:var(--ink2); margin:2px 0 4px; }} .key {{ margin-right:14px; }}
.key i {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }}
table {{ border-collapse:collapse; font-size:12px; margin:6px 0; }} th, td {{ border-bottom:1px solid var(--rule); padding:4px 10px; text-align:left; }}
th {{ color:var(--ink2); font-weight:600; }} .note {{ color:var(--ink2); max-width:900px; }}
.synthetic {{ border:2px dashed var(--ink2); padding:8px 12px; font-weight:600; margin-bottom:4px; }}
footer {{ padding:16px 32px 40px; color:var(--ink2); font-size:12px; }}
</style></head><body>
<header><h1>Specialty infusion FP&amp;A scorecard: CY2027 plan</h1>
<p>Public CMS / CDC / Census data; illustrative practice drivers are labelled assumptions. Mirrors the pages of the
Power BI model in <code>powerbi/</code> (not opened in Power BI Desktop). Price basis: 2027 (payment on lagged ASP, purchase at current ASP).</p></header>
<nav>{nav}</nav>{body}
<footer>Generated by <code>make scorecard</code> from outputs/*.json and exports/*.csv. Hover any bar or point for its value.
KPI cross-check: {len(kp)} DAX measures have SQL twins (outputs/kpis.json).</footer>
</body></html>"""


def main() -> None:
    (DOCS / "scorecard.html").write_text(build())
    print("docs/scorecard.html written")


if __name__ == "__main__":
    main()
