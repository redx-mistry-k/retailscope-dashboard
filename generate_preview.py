"""Generate an offline HTML snapshot of the Streamlit dashboard's default figures.

This is a static scenario preview with interactive chart hover/zoom. Filtering and
PDF generation are provided by the full Streamlit app in app.py.
"""
from __future__ import annotations

import ast
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.offline.offline import get_plotlyjs

from retailscope.data import REGIONS, STORE_TYPES, draw_sample, generate_population
from retailscope.reporting import format_inr_crore
from retailscope.stats import estimate_market, summarize_regions


ROOT = Path(__file__).parent


def chart_functions():
    """Load only the shared chart definitions, without importing Streamlit."""
    src = ast.parse((ROOT / "app.py").read_text(encoding="utf8"))
    names = {"beautify", "sales_chart", "coverage_chart", "store_mix_chart", "region_map"}
    nodes = [n for n in src.body if isinstance(n, ast.FunctionDef) and n.name in names]
    context = {
        "pd": pd, "go": go, "REGIONS": REGIONS, "STORE_TYPES": STORE_TYPES,
        "TEAL": "#0B7D89", "NAVY": "#14283E", "MUTED": "#718196",
        "PINK": "#DDA3B5", "BLUE": "#64A5D7", "BACKGROUND": "#FAFCFE",
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<preview-charts>", "exec"), context)
    return context


def main():
    pop = generate_population(9600, seed=2026)
    sample = draw_sample(pop, 720, seed=77)
    est = estimate_market(pop, sample)
    regional = summarize_regions(pop, sample)
    f = chart_functions()
    charts = [
        ("Estimated monthly market sales", f["sales_chart"](regional)),
        ("Sampling frame vs sample allocation", f["coverage_chart"](regional)),
        ("Store format representation", f["store_mix_chart"](pop, sample)),
        ("Geographic market comparison", f["region_map"](regional)),
    ]
    plot_divs = "".join(
        f'<section class="panel"><h2>{escape(title)}</h2>'
        + fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})
        + "</section>" for title, fig in charts
    )
    tbody = "".join(
        f"<tr><td>{escape(r.region)}</td><td>{r.universe_stores:,.0f}</td>"
        f"<td>{r.sampled_stores:,.0f}</td><td>{format_inr_crore(r.market_sales_inr)}</td>"
        f"<td>{r.cv_pct:.2f}%</td></tr>"
        for r in regional.itertuples(index=False)
    )
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RetailScope | Offline Dashboard Preview</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#FAFCFE;color:#14283E;font:15px Arial,sans-serif}}
header{{background:#14283E;color:white;padding:25px max(24px,calc((100vw - 1300px)/2))}}
header .brand{{color:#67D3D4;font-size:12px;font-weight:800;letter-spacing:2px}}
header h1{{font-size:34px;margin:9px 0}}header p{{color:#BED0DD;line-height:1.5}}
main{{max-width:1300px;margin:auto;padding:23px}}
.warning{{padding:12px 17px;border-radius:12px;background:#FFF8E8;color:#795F1C;margin:15px 0}}
.kpis{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:24px 0}}
.kpi{{padding:21px;border:1px solid #E2E9EF;border-radius:14px;background:white}}
.kpi small{{color:#62758B;font-weight:700}}.kpi strong{{display:block;margin-top:9px;font-size:24px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}
.panel{{background:white;padding:13px;border:1px solid #E2E9EF;border-radius:14px;min-width:0}}
h2{{font-size:17px;margin:11px 13px;color:#14283E}}table{{border-collapse:collapse;width:100%;margin:10px 0 35px}}
th,td{{padding:12px;text-align:left;border-bottom:1px solid #E1E9F0}}
th{{background:#14283E;color:white}}a{{color:#0B7D89;font-weight:700}}
@media(max-width:960px){{.kpis{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}}}
@media(max-width:600px){{.kpis{{grid-template-columns:1fr 1fr}}.kpi strong{{font-size:17px}}table{{font-size:12px}}}}
</style><script>{get_plotlyjs()}</script></head><body>
<header><div class="brand">RETAILSCOPE / STATISTICAL MARKET INTELLIGENCE</div>
<h1>FMCG market overview</h1><p>Tamil Nadu • Demonstration dashboard snapshot • Stratified sample (n = 720)</p></header>
<main><div class="warning"><b>Simulated data.</b> This offline preview has working chart hover/zoom but static filters. Run <code>streamlit run app.py</code> for interactive filtering and live report exports.</div>
<div class="kpis"><div class="kpi"><small>ESTIMATED MONTHLY SALES</small><strong>{format_inr_crore(est.estimate_inr)}</strong></div>
<div class="kpi"><small>95% CONFIDENCE HALF-WIDTH</small><strong>± {format_inr_crore((est.ci_high_inr-est.ci_low_inr)/2)}</strong></div>
<div class="kpi"><small>ASSUMED UNIVERSE</small><strong>{est.universe_n:,} stores</strong></div>
<div class="kpi"><small>SAMPLE / RESPONSE</small><strong>{est.sampled_n:,} / {est.response_rate_pct:.1f}%</strong></div></div>
<div class="grid">{plot_divs}</div>
<section class="panel" style="margin-top:18px"><h2>Market comparison table</h2>
<div style="overflow-x:auto"><table><thead><tr><th>Region</th><th>Universe</th><th>Sample</th><th>Monthly sales</th><th>CV</th></tr></thead>
<tbody>{tbody}</tbody></table></div></section>
<p><a href="RetailScope_Stakeholder_Report.pdf">Open sample stakeholder report (PDF)</a> ·
<a href="RetailScope_Regional_Estimates.csv">Open regional results (CSV)</a></p>
<p style="color:#6B7E90;font-size:12px">Not a real market estimate; no affiliation with NielsenIQ. All data and results are synthetic.</p>
</main></body></html>"""
    output = ROOT / "sample_outputs" / "RetailScope_Dashboard_Preview.html"
    output.write_text(html, encoding="utf-8")
    print(f"Created {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
