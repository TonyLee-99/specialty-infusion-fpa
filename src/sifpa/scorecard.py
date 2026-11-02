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
    rcm = J("rcm_kpis_SYNTHETIC.json")
    conv = J("biosimilar_conversion.json")
    tor = J("tornado.json")
    base = sc["scenarios"]["base"]

    # ---- page 1: executive ----
    p1 = "".join([
        tile("CY2027 base contribution (illustrative 12-chair suite)", money(base["annual"]["contribution"]),
             f'{base["annual"]["administrations"]:,} infusions/yr'),
        tile("Contribution per infusion: Medicare FFS", money(m["medicare_ffs_per_admin"]["contribution"], 2),
             f'drug margin {pct(m["medicare_drug_margin_pct_of_drug_revenue"])} of drug revenue'),
        tile("Contribution per infusion: commercial (assumed contract)", money(m["commercial_per_admin"]["contribution"], 2),
             "ASP + 20% assumption; widest tornado bar"),
        tile("Policy shock (2028 run-rate)", money(sc["scenarios"]["policy_shock"]["annual"]["contribution"] - base["annual"]["contribution"]),
             "MFP Orencia/Entyvio + 15% white bagging"),
        tile("Biosimilar push", money(sc["scenarios"]["biosimilar_push"]["annual"]["contribution"] - base["annual"]["contribution"]),
             "to 80% biosimilar on 4 molecules"),
        tile("Allowed vs payment limit (2024, measured)", pct(m["realization"]["allowed_weighted_ratio_2024"]),
             "unexplained gap; downside sensitivity"),
    ])
    scen_rows = [(n.replace("_", " "), [s["annual"]["contribution"]]) for n, s in sc["scenarios"].items()]
    p1 += '<h3>CY2027 annual contribution by scenario</h3>' + hbars(scen_rows, [("Contribution", S1)], money)
    bars = tor["bars"][:8]
    tor_rows = [(b["driver"].replace("_", " ")[:30], [b["contribution_at_low"] - tor["base_contribution"],
                                                     b["contribution_at_high"] - tor["base_contribution"]]) for b in bars]
    p1 += ('<h3>Tornado: change in annual contribution, each assumption at its documented low / high</h3>'
           + hbars(tor_rows, [("at low value", S2), ("at high value", S1)], money))

    # ---- page 2: pricing & margin ----
    hist = pd.DataFrame(conv["_infliximab_history"])
    names = {"J1745": "Remicade J1745", "Q5103": "Inflectra Q5103", "Q5104": "Renflexis Q5104", "Q5121": "Avsola Q5121"}
    series = []
    for code, color in zip(names, (S1, S2, S3, S4), strict=True):
        g = hist[hist["hcpcs"] == code]
        series.append((names[code], color, list(zip(g["payment_quarter"], g["payment_limit"], strict=True))))
    p2 = '<h3>Infliximab: Medicare payment limit per 10 mg, by product (CMS ASP files, 2017Q1-2026Q4)</h3>'
    p2 += lines(series, lambda v: f"${v:,.0f}")
    cph = [r for r in m["contribution_per_chair_hour"] if r["mix_share"] > 0][:12]
    p2 += ('<h3>Contribution per chair-hour, infusions in the practice mix (reference / single-source, 2026Q4 prices)</h3>'
           + hbars([(f'{r["molecule"]} {r["hcpcs"]}', [r["medicare_per_chair_hour"], r["commercial_per_chair_hour"]]) for r in cph],
                   [("Medicare FFS", S1), ("Commercial (assumed)", S2)], money))
    conv_tbl = pd.DataFrame([{"molecule": k, "reference": v["reference"], "best biosimilar (payer-mix margin)": v["best_biosimilar"],
                              "switch: Medicare $/infusion": round(v["switch_delta_medicare_per_admin"]),
                              "switch: commercial $/infusion": round(v["switch_delta_commercial_per_admin"]),
                              "IRA +8% expiry hit $/infusion": round(v["ira_addon_expiry_hit_per_admin"])}
                             for k, v in conv.items() if not k.startswith("_")])
    p2 += "<h3>Biosimilar conversion economics per infusion</h3>" + table(conv_tbl)

    # ---- page 3: forecast & scenarios ----
    qa, an = fc["quarterly_asp"], fc["annual"]
    models = ["naive", "seasonal_naive", "drift", "ets_damped"]
    p3 = (f'<h3>Backtest MAPE: quarterly ASP payment limit ({qa["n_series"]} drugs, origins {qa["first_origin"]}-{qa["last_origin"]}, h = 1-4)</h3>'
          + hbars([(mm.replace("_", " "), [qa["mape_by_model"][mm]]) for mm in models], [("MAPE", S1)], pct))
    p3 += (f'<h3>Backtest MAPE: annual in-office volume and allowed $ ({an["n_series"]} series, origins {an["origins"][0]}-{an["origins"][-1]}, h = 1-2)</h3>'
           + hbars([(mm.replace("_", " "), [an["mape_by_model"][mm]]) for mm in ("naive", "drift", "ets_damped")], [("MAPE", S1)], pct))
    cov = pd.DataFrame(qa["pi80_coverage_eval"] + an["pi80_coverage_eval"])
    cov.insert(0, "problem", ["quarterly ASP"] * len(qa["pi80_coverage_eval"]) + ["annual volume"] * len(an["pi80_coverage_eval"]))
    cov["coverage_80"] = cov["coverage_80"].map(pct)
    p3 += "<h3>80% prediction intervals: coverage on held-out origins (calibrated on earlier origins)</h3>" + table(cov)
    ext = fc["external_2025"]
    p3 += (f'<p class="note">Out-of-sample 2025 check (all-settings Part B spend, {ext["n_molecules"]} molecules, never used in fitting): '
           f'MAPE naive {pct(ext["mape_2025"]["naive"])}, drift {pct(ext["mape_2025"]["drift"])}, damped ETS {pct(ext["mape_2025"]["ets_damped"])}.</p>')

    # ---- page 4: benchmark & market ----
    top = pd.DataFrame(mk["market_top10"])
    top["market"] = top["market"] + top["partial_market"].map({True: " (in-region part only)", False: ""})
    top = top[["rank", "market", "p_top10", "population", "specialists_per_100k", "infusion_billers_per_100k",
               "miles_to_columbus_site"]]
    p4 = (f'<h3>White space: top 10 markets of {mk["markets"]["n_eligible"]} eligible (P(top 10) over {mk["n_weight_draws"]:,} random weightings)</h3>'
          + hbars([(r.market[:28], [r.p_top10]) for r in top.itertuples()], [("P(top 10)", S1)], pct))
    top["p_top10"] = top["p_top10"].map(pct)
    top["population"] = top["population"].map("{:,}".format)
    p4 += table(top)
    share = pd.read_csv(EXPORTS / "fact_market_biosimilar_share.csv")
    inf = share[(share["molecule"] == "infliximab")].sort_values("biosimilar_share", ascending=False)
    p4 += ("<h3>Infliximab biosimilar share of in-office administrations, 2024 (Medicare FFS geography totals)</h3>"
           + hbars([(r.geo, [r.biosimilar_share]) for r in inf.itertuples()], [("Biosimilar share", S1)], pct))
    vs = bm["biosimilar_vs_peer_counts"]
    p4 += (f'<p class="note">Provider level ({bm["n_providers_scored"]:,} clinicians scored): {pct(bm["share_provider_molecule_censored"])} of '
           f'provider-molecule rates are censored by CMS cell suppression, so only {vs.get("above_peer", 0)} providers are distinguishably '
           f'above and {vs.get("below_peer", 0)} below their specialty median on biosimilar adoption. Infusing providers: median '
           f'{pct(bm["infusing_median_drug_share"])} of Medicare allowed is drugs.</p>')

    # ---- page 5: RCM SYNTHETIC ----
    p5 = '<div class="synthetic">SYNTHETIC DATA: method demo only. No business conclusion is drawn from this page.</div>'
    p5 += "".join([tile("Clean-claim rate (SYNTHETIC)", pct(rcm["clean_claim_rate"])),
                   tile("Initial denial rate (SYNTHETIC)", pct(rcm["denial_rate"])),
                   tile("Days in AR (SYNTHETIC)", f'{rcm["days_in_ar"]:.1f}'),
                   tile("Net collection rate (SYNTHETIC)", pct(rcm["net_collection_rate"]))])
    p5 += ("<h3>Initial denials by CARC group, share of first remits (SYNTHETIC)</h3>"
           + hbars(list((k, [v]) for k, v in rcm["denial_rate_by_carc_group"].items()), [("share", S3)], pct))

    sections = [("exec", "Executive summary", p1), ("pricing", "Pricing, ASP lag and margin per infusion", p2),
                ("forecast", "Forecasts and 2027 scenarios", p3), ("market", "Benchmark and market white space", p4),
                ("rcm", "Revenue cycle (SYNTHETIC)", p5)]
    nav = "".join(f'<a href="#{i}">{esc(t)}</a>' for i, t, _ in sections)
    body = "".join(f'<section id="{i}"><h2>{esc(t)}</h2><div class="tiles">{c}</div></section>'
                   if i in ("exec", "rcm") else f'<section id="{i}"><h2>{esc(t)}</h2>{c}</section>' for i, t, c in sections)
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
Power BI model in <code>powerbi/</code> (not opened in Power BI Desktop). Prices: CMS ASP {esc(m["price_quarter"])}.</p></header>
<nav>{nav}</nav>{body}
<footer>Generated by <code>make scorecard</code> from outputs/*.json and exports/*.csv. Hover any bar or point for its value.
KPI cross-check: {len(kp)} DAX measures have SQL twins (outputs/kpis.json).</footer>
</body></html>"""


def main() -> None:
    (DOCS / "scorecard.html").write_text(build())
    print("docs/scorecard.html written")


if __name__ == "__main__":
    main()
