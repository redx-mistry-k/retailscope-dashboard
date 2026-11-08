"""RetailScope | Interactive, reproducible retail survey reporting dashboard.

Run locally: streamlit run app.py
All market figures are synthetic and not NIQ production data.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from retailscope.data import REGIONS, STORE_TYPES, draw_sample, generate_population
from retailscope.design import compare_allocations, simulate_designs
from retailscope.reporting import build_pdf_report, export_csv, format_inr_crore
from retailscope.stats import (
    compare_with_synthetic_truth, estimate_market, flag_quality_issues,
    summarize_regions,
)
from retailscope.universe import simulate_two_lists

TEAL = "#0B7D89"
NAVY = "#14283E"
MUTED = "#718196"
PINK = "#DDA3B5"
BLUE = "#64A5D7"
BACKGROUND = "#FAFCFE"

st.set_page_config(page_title="RetailScope | Market Intelligence", page_icon="🧭",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; max-width: 1450px; padding-bottom: 3rem;}
.stApp {background: #FAFCFE;}
[data-testid="stSidebar"] {background: #F1F6F8;}
[data-testid="stMetric"] {background:#fff; border:1px solid #E1EAF0; border-radius:14px; padding:17px 17px 13px; box-shadow: 0 3px 13px rgba(20,40,62,.035);}
[data-testid="stMetricLabel"] {font-weight:600; color:#617287;}
[data-testid="stMetricValue"] {font-size:1.55rem; color:#14283E;}
h1, h2, h3 {color:#14283E; letter-spacing:-.018em;}
[data-testid="stTabs"] button {font-weight:600;}
.smallcaps {font-size:.75rem; font-weight:800; letter-spacing:.11em; color:#0B7D89;}
.hero-title {font-size:2.4rem; font-weight:800; letter-spacing:-.045em; color:#14283E; line-height:1.1; margin:.3rem 0;}
.hero-sub {color:#60768B; font-size:1rem; margin-top:.4rem;}
.pill {display:inline-block;padding:5px 11px;background:#E8F4F5;color:#0B7D89;border-radius:50px;font-size:.76rem;font-weight:700;margin-right:6px;}
.disclaimer {background:#FFF8E8;border:1px solid #F0E2B8;color:#866414;border-radius:11px;padding:10px 14px;font-size:.88rem;margin:.7rem 0 1.4rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_population() -> pd.DataFrame:
    return generate_population(9600, seed=2026)


@st.cache_data(show_spinner=False)
def load_sample(sample_size: int, random_seed: int) -> pd.DataFrame:
    return draw_sample(load_population(), target_n=sample_size, seed=random_seed)


def beautify(fig: go.Figure, height: int = 375) -> go.Figure:
    fig.update_layout(
        height=height, paper_bgcolor=BACKGROUND, plot_bgcolor=BACKGROUND,
        font=dict(family="Arial", color=NAVY, size=12),
        margin=dict(t=28, b=27, l=12, r=12),
        legend=dict(orientation="h", y=-.22, x=0),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    fig.update_xaxes(showline=False, gridcolor="#EBF0F3", zeroline=False)
    fig.update_yaxes(showline=False, gridcolor="#EBF0F3", zeroline=False)
    return fig


def sales_chart(regional: pd.DataFrame) -> go.Figure:
    values = regional.market_sales_inr / 1e7
    upper = (regional.ci_high_inr - regional.market_sales_inr) / 1e7
    lower = (regional.market_sales_inr - regional.ci_low_inr) / 1e7
    fig = go.Figure(go.Bar(
        x=regional.region, y=values, name="Estimated sales", marker_color=TEAL,
        marker_line_width=0,
        error_y=dict(type="data", symmetric=False, array=upper, arrayminus=lower,
                     thickness=1.4, width=5, color=NAVY),
        customdata=regional[["universe_stores", "sampled_stores", "cv_pct"]].to_numpy(),
        hovertemplate=("<b>%{x}</b><br>Monthly sales: %{y:,.1f} Cr"
                       "<br>Universe stores: %{customdata[0]:,}"
                       "<br>Sample: %{customdata[1]:,}"
                       "<br>CV: %{customdata[2]:.2f}%<extra></extra>"),
    ))
    fig.update_layout(yaxis_title="Estimated monthly sales (INR Cr)", xaxis_title="")
    return beautify(fig)


def coverage_chart(regional: pd.DataFrame) -> go.Figure:
    total_universe = max(int(regional.universe_stores.sum()), 1)
    total_sample = max(int(regional.sampled_stores.sum()), 1)
    fig = go.Figure([
        go.Bar(name="Universe share", x=regional.region,
               y=100 * regional.universe_stores / total_universe, marker_color=BLUE),
        go.Bar(name="Sample share", x=regional.region,
               y=100 * regional.sampled_stores / total_sample, marker_color=TEAL),
    ])
    fig.update_layout(barmode="group", yaxis_title="Share of stores (%)", xaxis_title="",
                      hovermode="x unified")
    return beautify(fig)


def store_mix_chart(population: pd.DataFrame, sample: pd.DataFrame) -> go.Figure:
    universe_mix = population.groupby("store_type").size().reindex(list(STORE_TYPES), fill_value=0)
    sample_mix = sample.groupby("store_type").size().reindex(list(STORE_TYPES), fill_value=0)
    fig = go.Figure([
        go.Bar(name="Universe share", x=universe_mix.index,
               y=100 * universe_mix / len(population), marker_color=BLUE),
        go.Bar(name="Sample share", x=sample_mix.index,
               y=100 * sample_mix / len(sample), marker_color=TEAL),
    ])
    fig.update_layout(barmode="group", yaxis_title="Store format share (%)", xaxis_title="")
    return beautify(fig)


def region_map(regional: pd.DataFrame) -> go.Figure:
    plot = regional.copy()
    plot["lat"] = plot.region.map(lambda r: REGIONS[r]["lat"])
    plot["lon"] = plot.region.map(lambda r: REGIONS[r]["lon"])
    sales = plot.market_sales_inr / 1e7
    sizes = 15 + 40 * (sales / max(sales.max(), 1)) ** .5
    fig = go.Figure(go.Scattergeo(
        lat=plot.lat, lon=plot.lon, text=plot.region,
        mode="markers+text", textposition="top center",
        textfont=dict(color=NAVY, size=11),
        marker=dict(size=sizes, color=TEAL, opacity=.8, line=dict(color="white", width=2)),
        customdata=plot[["market_sales_inr", "sampled_stores", "coverage_pct"]].to_numpy(),
        hovertemplate=("<b>%{text}</b><br>Monthly market sales: INR %{customdata[0]:,.0f}"
                       "<br>Sample size: %{customdata[1]:,}"
                       "<br>Store coverage: %{customdata[2]:.1f}%<extra></extra>"),
    ))
    fig.update_geos(
        projection_type="mercator", showland=True, landcolor="#EEF3F5",
        showcountries=True, countrycolor="#C8D4DD",
        showcoastlines=True, coastlinecolor="#B8D1DC",
        showocean=True, oceancolor="#E8F4F8",
        lataxis_range=[8, 14.2], lonaxis_range=[76.1, 81.1],
        bgcolor=BACKGROUND, resolution=50,
    )
    fig.update_layout(height=490, paper_bgcolor=BACKGROUND,
                      margin=dict(l=0, r=0, t=10, b=10), showlegend=False)
    return fig


with st.sidebar:
    st.markdown("### 🧭 RetailScope")
    st.caption("STATISTICAL MARKET INTELLIGENCE")
    st.divider()
    st.subheader("Market filters")
    selected_regions = st.multiselect(
        "Regions", list(REGIONS), default=list(REGIONS),
        help="Changes both the assumed universe and the surveyed subset."
    )
    selected_types = st.multiselect(
        "Store formats", list(STORE_TYPES), default=list(STORE_TYPES)
    )
    st.divider()
    st.subheader("Survey scenario")
    sample_n = st.slider("Total surveyed stores", min_value=240, max_value=1440,
                         value=720, step=60)
    seed = st.number_input("Sampling random seed", min_value=1, max_value=10_000,
                           value=77, step=1)
    confidence = st.select_slider("Confidence level", options=[0.90, 0.95, 0.99],
                                   value=0.95,
                                   format_func=lambda c: f"{c:.0%}")
    st.divider()
    st.caption("**Research scenario:** synthetic Tamil Nadu-style FMCG stores")
    st.caption("**Source:** Reproducible synthetic population")
    st.caption("**Sales period:** Illustrative monthly snapshot")
    st.caption("This is a portfolio demonstration, not NIQ production data.")

if not selected_regions or not selected_types:
    st.warning("Select at least one region and one store format in the sidebar.")
    st.stop()

population_all = load_population()
sample_all = load_sample(sample_n, int(seed))
mask_p = population_all.region.isin(selected_regions) & population_all.store_type.isin(selected_types)
mask_s = sample_all.region.isin(selected_regions) & sample_all.store_type.isin(selected_types)
population = population_all.loc[mask_p].copy()
sample = sample_all.loc[mask_s].copy()
overall = estimate_market(population, sample, confidence)
regional = summarize_regions(population, sample, confidence)
quality = flag_quality_issues(sample)

st.markdown('<div class="smallcaps">MARKET INTELLIGENCE / SURVEY ANALYTICS</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-title">RetailScope <span style="color:#0B7D89">/</span> Market Overview</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Evidence-led retail sample reporting for a synthetic Tamil Nadu FMCG market.</div>', unsafe_allow_html=True)
st.markdown('<span class="pill">FY 2026 DEMO</span><span class="pill">STRATIFIED SAMPLING</span><span class="pill">REPRODUCIBLE</span>', unsafe_allow_html=True)
st.markdown('<div class="disclaimer"><b>Demonstration only:</b> Every store, sales figure and estimate is simulated. Not affiliated with NielsenIQ.</div>', unsafe_allow_html=True)

if overall.validity != "OK":
    st.warning(overall.validity + ". Consider increasing the sample size or switching the random seed.")

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Estimated monthly sales", format_inr_crore(overall.estimate_inr))
with k2:
    half_width = (overall.ci_high_inr - overall.ci_low_inr) / 2
    st.metric(f"{confidence:.0%} confidence interval", f"± {format_inr_crore(half_width)}")
with k3:
    st.metric("Assumed universe", f"{overall.universe_n:,} stores")
with k4:
    st.metric("Sample / response rate", f"{overall.sampled_n:,} / {overall.response_rate_pct:.1f}%")

st.caption(f"Selected market: {len(selected_regions)} regions · {len(selected_types)} formats · "
           f"sample coverage {overall.coverage_pct:.1f}% · CV "
           f"{overall.cv_pct:.2f}%" if pd.notna(overall.cv_pct) else "Precision unavailable for these filters.")

t_overview, t_sampling, t_estimates, t_geography, t_quality, t_reports = st.tabs([
    "📊  Overview", "🎯  Sampling", "📈  Market Estimates", "📍  Geographic Analysis", "🛡️  Data Quality", "📄  Reports"
])

with t_overview:
    st.subheader("Regional retail performance")
    left, right = st.columns([1.75, 1], gap="large")
    with left:
        st.markdown("**Monthly estimated sales by region**")
        st.plotly_chart(sales_chart(regional), width="stretch",
                        config={"displayModeBar": False})
    with right:
        st.markdown("**Regional contribution**")
        fig = go.Figure(go.Pie(
            labels=regional.region, values=regional.market_sales_inr,
            hole=.66, marker=dict(colors=[TEAL, BLUE, "#9ECFC8", PINK, "#6F85AD", "#A8B9CA"]),
            textinfo="percent", textposition="outside",
            hovertemplate="%{label}<br>%{percent}<extra></extra>",
        ))
        fig.update_layout(height=375, showlegend=True, margin=dict(l=7,r=7,t=28,b=14),
                          paper_bgcolor=BACKGROUND, legend=dict(orientation="h",y=-.14))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.markdown("**Regional estimate detail**")
    table = regional[["region", "universe_stores", "sampled_stores", "response_rate_pct",
                      "market_sales_inr", "ci_low_inr", "ci_high_inr", "cv_pct"]].copy()
    for col in ["market_sales_inr", "ci_low_inr", "ci_high_inr"]:
        table[col] = table[col] / 1e7
    st.dataframe(table, width="stretch", hide_index=True, column_config={
        "region": "Market", "universe_stores": "Universe stores", "sampled_stores": "Sample",
        "response_rate_pct": st.column_config.NumberColumn("Response %", format="%.1f"),
        "market_sales_inr": st.column_config.NumberColumn("Sales (₹ Cr)", format="%.2f"),
        "ci_low_inr": st.column_config.NumberColumn("CI lower (₹ Cr)", format="%.2f"),
        "ci_high_inr": st.column_config.NumberColumn("CI upper (₹ Cr)", format="%.2f"),
        "cv_pct": st.column_config.NumberColumn("CV %", format="%.2f"),
    })
    st.caption("Error bars are normal-approximation confidence intervals for sampling uncertainty, not forecast ranges.")

with t_sampling:
    st.subheader("Sample design & representation")
    st.caption("An independent simple random sample is drawn within each region × store-format stratum.")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**Region allocation comparison**")
        st.plotly_chart(coverage_chart(regional), width="stretch",
                        config={"displayModeBar": False})
    with c2:
        st.markdown("**Store-format allocation comparison**")
        st.plotly_chart(store_mix_chart(population, sample), width="stretch",
                        config={"displayModeBar": False})
    mix = (population.groupby(["region", "store_type"]).size().rename("universe_stores")
           .to_frame().join(sample.groupby(["region", "store_type"]).size().rename("sampled_stores"))
           .fillna(0).reset_index())
    mix["sampled_stores"] = mix.sampled_stores.astype(int)
    mix["sampling_fraction_pct"] = 100 * mix.sampled_stores / mix.universe_stores
    st.markdown("**Stratum-level sample allocation**")
    st.dataframe(mix, hide_index=True, width="stretch", column_config={
        "region": "Region", "store_type": "Store format", "universe_stores": "Universe",
        "sampled_stores": "Selected", "sampling_fraction_pct": st.column_config.NumberColumn("Sample fraction %", format="%.1f")
    })
    st.info("A high sample fraction is not the same as representativeness. Stratification and unbiased field execution matter. This demonstration assumes the finite store universe is known.")

    st.divider()
    st.subheader("Interactive sample designer")
    st.caption("Compare one overall simple random sample with proportional and Neyman allocation across the selected region × format strata. Neyman uses stratum sales standard deviations from the known synthetic population; a real study would need pilot estimates.")
    design_max = len(population)
    design_min = min(design_max, max(2, 2 * len(population.groupby(["region", "store_type"], observed=True))))
    design_n = st.slider("Designer sample size", min_value=design_min,
                         max_value=design_max, value=min(max(sample_n, design_min), design_max),
                         step=1, help="Total stores to select from the currently filtered synthetic universe.")
    allocation = compare_allocations(population, design_n)
    allocation["stratum"] = allocation.region + " / " + allocation.store_type
    allocation_chart = go.Figure([
        go.Bar(name="Proportional", x=allocation.stratum, y=allocation.proportional_n, marker_color=BLUE),
        go.Bar(name="Neyman", x=allocation.stratum, y=allocation.neyman_n, marker_color=TEAL),
    ])
    allocation_chart.update_layout(barmode="group", xaxis_title="Region / store format", yaxis_title="Allocated stores")
    st.plotly_chart(beautify(allocation_chart, height=410), width="stretch",
                    config={"displayModeBar": False})
    st.dataframe(allocation[["region", "store_type", "universe_stores", "proportional_n", "neyman_n"]],
                 hide_index=True, width="stretch")
    st.caption("Simple random sampling has no fixed stratum quotas. Both stratified designs enforce at least two sampled stores per nonempty stratum where feasible.")
    simulations = st.slider("Simulation repetitions", 20, 300, 100, step=20,
                            help="Repeated draws on the selected known synthetic universe; more draws give a steadier comparison.")
    if st.button("Run design simulation", type="primary"):
        with st.spinner("Simulating repeated samples..."):
            comparison = simulate_designs(population, design_n, simulations, int(seed), confidence)
        st.session_state["design_comparison"] = comparison
        st.session_state["design_signature"] = (tuple(selected_regions), tuple(selected_types), design_n, simulations, int(seed), confidence)
    signature = (tuple(selected_regions), tuple(selected_types), design_n, simulations, int(seed), confidence)
    if st.session_state.get("design_signature") == signature:
        comparison = st.session_state["design_comparison"]
        st.markdown("**Repeated-sample performance**")
        st.dataframe(comparison, hide_index=True, width="stretch", column_config={
            "bias_pct": st.column_config.NumberColumn("Bias % of truth", format="%.2f"),
            "rmse_pct": st.column_config.NumberColumn("RMSE % of truth", format="%.2f"),
            "coverage_pct": st.column_config.NumberColumn("CI coverage %", format="%.1f"),
            "mean_ci_width_pct": st.column_config.NumberColumn("Mean CI width % of truth", format="%.1f"),
        })
        sim_fig = go.Figure([
            go.Bar(x=comparison.design, y=comparison.rmse_pct, marker_color=[BLUE, TEAL, PINK],
                   hovertemplate="%{x}<br>RMSE: %{y:.2f}% of truth<extra></extra>"),
        ])
        sim_fig.update_layout(yaxis_title="RMSE (% of synthetic truth)")
        st.plotly_chart(beautify(sim_fig, height=300), width="stretch",
                        config={"displayModeBar": False})
        st.caption("Bias is mean signed error; RMSE combines bias and spread. Coverage is the fraction of approximate intervals containing known synthetic truth. Monte Carlo results vary with seed and repetitions. Simulations assume full response for a fair allocation comparison.")

with t_estimates:
    st.subheader("Market estimates & uncertainty")
    st.write("The selected total expands responding-store mean sales by the known synthetic store count in each region × format stratum. Regional totals add to the selected market total.")
    m1, m2, m3 = st.columns(3)
    m1.metric("Estimated monthly sales", format_inr_crore(overall.estimate_inr))
    m2.metric(f"{confidence:.0%} interval", f"{format_inr_crore(overall.ci_low_inr)} to {format_inr_crore(overall.ci_high_inr)}")
    m3.metric("Coefficient of variation", f"{overall.cv_pct:.2f}%" if pd.notna(overall.cv_pct) else "Unavailable")
    st.plotly_chart(sales_chart(regional), width="stretch", config={"displayModeBar": False}, key="estimates_sales")
    st.dataframe(regional, hide_index=True, width="stretch")
    st.info("Intervals quantify approximate sampling uncertainty under random response within strata and a known, complete synthetic universe. They exclude frame, measurement and nonresponse bias. An interval is withheld when a stratum has fewer than two responses.")
    st.divider()
    st.subheader("Store universe estimation lab")
    st.caption("Two independently generated synthetic store lists illustrate a Chapman capture–recapture point estimate. This is separate from the known frame counts used above for sales expansion.")
    p1, p2 = st.columns(2)
    with p1:
        probability_a = st.slider("List A inclusion probability", .10, .90, .45, .05)
    with p2:
        probability_b = st.slider("List B inclusion probability", .10, .90, .55, .05)
    universe_demo = simulate_two_lists(population, probability_a, probability_b, int(seed))
    u1, u2, u3, u4 = st.columns(4)
    u1.metric("List A stores", f"{universe_demo.list_a_n:,}")
    u2.metric("List B stores", f"{universe_demo.list_b_n:,}")
    u3.metric("Matched stores", f"{universe_demo.overlap_n:,}")
    u4.metric("Estimated universe", f"{universe_demo.estimated_n:,.0f}" if pd.notna(universe_demo.estimated_n) else "Unavailable")
    if pd.notna(universe_demo.estimated_n):
        st.caption(f"Known synthetic truth: {len(population):,} stores · point-estimate error: {100 * (universe_demo.estimated_n / len(population) - 1):+.1f}%")
    else:
        st.warning("Too few matched stores to show a credible two-list point estimate.")
    st.caption("Method: ((A + 1) × (B + 1) / (overlap + 1)) − 1. It assumes a closed universe, independent lists, equal inclusion chances within the selected domain, and accurate record matching. No uncertainty interval is shown for this illustrative count; count uncertainty is not propagated into the sales interval.")

with t_geography:
    st.subheader("Geographic market comparison")
    c1, c2 = st.columns([1.3, 1], gap="large")
    with c1:
        st.markdown("**Market locations · bubble size = estimated sales**")
        st.plotly_chart(region_map(regional), width="stretch",
                        config={"displayModeBar": False})
        st.caption("Markers are approximate city-centre coordinates, not actual surveyed store positions.")
    with c2:
        st.markdown("**Market ranking and precision**")
        geography = regional[["region", "market_sales_inr", "coverage_pct", "cv_pct"]].copy()
        geography["market_sales_inr"] /= 1e7
        st.dataframe(geography, hide_index=True, width="stretch",
                     column_config={
                         "region": "Region",
                         "market_sales_inr": st.column_config.NumberColumn("Estimated ₹ Cr", format="%.1f"),
                         "coverage_pct": st.column_config.ProgressColumn("Sample coverage %", min_value=0, max_value=100, format="%.1f"),
                         "cv_pct": st.column_config.NumberColumn("CV %", format="%.2f"),
                     })
        st.markdown("**How to interpret this view**")
        st.write("Compare sales estimates alongside coefficients of variation (CV). "
                 "Larger markets are not necessarily more precise, and sample fractions "
                 "should not be interpreted as market penetration.")

with t_quality:
    st.subheader("Survey quality monitoring")
    missing = int(quality.missing_sales.sum())
    outliers = int(quality.possible_outlier.sum())
    invalid = int(quality.invalid_sales.sum())
    dups = int(quality.duplicate_store_id.sum())
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Missing sales", missing)
    q2.metric("Potential outliers", outliers)
    q3.metric("Invalid negative sales", invalid)
    q4.metric("Duplicate rows", dups)
    st.caption("Potential outliers use within-format robust log-sales deviation. They are review flags, not confirmed errors and are not automatically excluded from estimates.")
    st.markdown("**Response rate by region**")
    region_response = regional[["region", "response_rate_pct"]].sort_values("response_rate_pct")
    fig = go.Figure(go.Bar(x=region_response.response_rate_pct, y=region_response.region,
                           orientation="h", marker_color=TEAL,
                           hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
    fig.update_layout(xaxis_title="Sales response rate (%)", yaxis_title="",
                      xaxis_range=[0, 100])
    st.plotly_chart(beautify(fig, height=300), width="stretch",
                    config={"displayModeBar": False})
    st.markdown("**Regional field coverage review**")
    coverage_review = regional[["region", "universe_stores", "sampled_stores",
                                "coverage_pct", "response_rate_pct", "status"]].copy()
    coverage_review["review_flag"] = coverage_review.apply(
        lambda row: "Review" if row.coverage_pct < 5 or row.response_rate_pct < 90 or row.status != "OK" else "OK",
        axis=1,
    )
    st.dataframe(coverage_review, hide_index=True, width="stretch")
    st.caption("The 5% sample-fraction and 90% response thresholds are illustrative review triggers, not universal statistical quality standards. Precision and field design still govern fitness for use.")
    st.markdown("**Flagged sample submissions**")
    flagged = quality.loc[quality.review_required,
        ["store_id", "region", "store_type", "response_status", "observed_sales_inr",
         "missing_sales", "possible_outlier", "invalid_sales", "duplicate_store_id"]]
    if flagged.empty:
        st.success("No issues flagged in the current selection.")
    else:
        st.dataframe(flagged, hide_index=True, width="stretch")
    st.warning("The nonresponse adjustment assumes responses are random within each region × store-format stratum. The displayed confidence intervals do not account for nonresponse bias or errors in the assumed universe.")

with t_reports:
    st.subheader("Export stakeholder-ready results")
    st.caption("Exports respect your currently selected regions, store formats, seed, sample size and confidence level.")
    pdf_bytes = build_pdf_report(
        market_name=" / ".join(selected_regions) if len(selected_regions) <= 2 else "Tamil Nadu (selected regions)",
        overall=overall, regional=regional, sample=sample, confidence=confidence,
        seed=int(seed), selected_types=selected_types,
    )
    e1, e2, e3 = st.columns(3)
    with e1:
        st.download_button("📄  Download executive PDF", data=pdf_bytes,
                           file_name="RetailScope_Stakeholder_Report.pdf", mime="application/pdf",
                           width="stretch", type="primary")
    with e2:
        st.download_button("📊  Download regional estimates", data=export_csv(regional),
                           file_name="RetailScope_Regional_Estimates.csv", mime="text/csv",
                           width="stretch")
    with e3:
        cols = ["store_id", "region", "store_type", "observed_sales_inr", "response_status"]
        st.download_button("🗂️  Download surveyed sample", data=export_csv(sample[cols]),
                           file_name="RetailScope_Survey_Sample.csv", mime="text/csv",
                           width="stretch")
    st.divider()
    st.subheader("Researcher's validation lab")
    st.caption("Synthetic simulation gives us a known benchmark to test the sampling method. In real-world retail research, true total sales would be unknown.")
    diagnostic = compare_with_synthetic_truth(population, overall)
    v1, v2, v3 = st.columns(3)
    v1.metric("Hidden synthetic truth", format_inr_crore(diagnostic["synthetic_truth_inr"]))
    v2.metric("Sampling error vs truth", f"{diagnostic['signed_error_pct']:+.2f}%")
    v3.metric("Truth inside selected CI?", "Yes" if diagnostic["within_ci"] else "No")
    with st.expander("Statistical methodology and limitations", expanded=False):
        st.markdown("""
**Sampling.** Simple random selection without replacement in each region × store format stratum, with near-proportional allocation and a minimum of 3 stores per stratum. The response model randomly omits approximately 2.5% of sampled sales submissions.

**Estimator.** For stratum *h*, use `estimated total = universe count (N_h) × responding-store mean sales`. Stratum estimates are summed to give the selected market estimate. The response adjustment assumes missing sales are random within each stratum.

**Variance.** Estimated sampling variance is the sum of `N_h² × (1 − r_h/N_h) × s_h² / r_h`, where `r_h` is the responding count and `s_h²` is sample variance among respondents. This treats respondents as if they were the effective simple random sample within each stratum. Confidence limits are estimate ± normal critical value × standard error.

**Limitations.** This is a learning demonstration of a known finite synthetic universe. It does not estimate the number of stores in an incomplete market frame, quantify universe-estimation uncertainty, model nonresponse bias, account for store clustering or fieldwork measurement error, or use real NIQ data. Confidence intervals are approximate.
        """)

st.markdown("---")
st.caption("RetailScope 1.0 • Python / Streamlit / Plotly • Synthetic sample design and statistical retail reporting • Built for portfolio and learning use")
