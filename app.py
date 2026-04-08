from __future__ import annotations

import pandas as pd
import streamlit as st

from portfolio_analysis import (
    build_report,
    filter_company_exposure,
    get_company_drilldown,
    get_dimension_drilldown,
    list_available_snapshot_dates,
)

try:
    import plotly.express as px
except ImportError:  # pragma: no cover - optional dependency
    px = None


st.set_page_config(
    page_title="PIE Portfolio Analysis",
    layout="wide",
)

st.markdown(
    """
    <style>
      :root {
        --accent: #0f4c81;
        --accent-soft: #dce8f5;
        --panel: #f7f4ee;
      }
      .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
      }
      .dashboard-banner {
        background: linear-gradient(135deg, #f7f4ee 0%, #edf4fb 65%, #dce8f5 100%);
        border: 1px solid rgba(15, 76, 129, 0.12);
        border-radius: 18px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
      }
      .dashboard-banner h1 {
        color: #13283d;
        font-size: 2rem;
        margin: 0;
      }
      .dashboard-banner p {
        color: #34506a;
        margin: 0.45rem 0 0 0;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

ETF_COLOR_MAP = {
    "SWDA": "#0f4c81",
    "EMIM": "#6a9ac4",
    "WSML": "#d89a3d",
}


@st.cache_data(show_spinner=False)
def load_report(snapshot_date: str) -> dict:
    return build_report(snapshot_date=snapshot_date)


def render_bar_chart(data: pd.DataFrame, label_column: str, title: str, top_n: int) -> None:
    chart_data = data.head(top_n).copy()
    if chart_data.empty:
        st.info("No data available for this view.")
        return

    chart_data = chart_data.iloc[::-1]
    if px is None:
        st.bar_chart(chart_data.set_index(label_column)["contribution_pct"])
        return

    fig = px.bar(
        chart_data,
        x="contribution_pct",
        y=label_column,
        orientation="h",
        text="contribution_pct",
        color="contribution_pct",
        color_continuous_scale=["#dce8f5", "#0f4c81"],
        title=title,
    )
    fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
    fig.update_layout(
        coloraxis_showscale=False,
        height=max(420, top_n * 28),
        margin=dict(l=0, r=12, t=42, b=12),
        xaxis_title="Portfolio contribution (%)",
        yaxis_title="",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_pie_chart(data: pd.DataFrame, names_column: str, values_column: str, title: str | None = None) -> None:
    if data.empty:
        st.info("No data available for this view.")
        return

    if px is None:
        st.info("Install plotly to view the ETF composition pie chart.")
        return

    fig = px.pie(
        data,
        names=names_column,
        values=values_column,
        title=title,
        hole=0.35,
        color=names_column,
        color_discrete_map=ETF_COLOR_MAP,
    )
    fig.update_traces(
        textposition="inside",
        texttemplate="%{label}<br>%{value:.1f}%",
        hovertemplate="%{label}: %{value:.2f}%<extra></extra>",
        sort=False,
    )
    fig.update_layout(
        showlegend=True,
        height=360,
        margin=dict(l=0, r=0, t=36 if title else 12, b=12),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_exposure_table(df: pd.DataFrame, label_column: str, height: int = 420) -> None:
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config={
            label_column: st.column_config.TextColumn(label_column.replace("_", " ").title()),
            "contribution_pct": st.column_config.NumberColumn(
                "Contribution",
                format="%.2f%%",
            ),
        },
    )


def render_weight_table(df: pd.DataFrame, label_column: str, height: int = 420) -> None:
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config={
            label_column: st.column_config.TextColumn(label_column.replace("_", " ").title()),
            "weight_pct": st.column_config.NumberColumn(
                "Weight",
                format="%.2f%%",
            ),
        },
    )


def render_etf_composition_table(df: pd.DataFrame, height: int = 220) -> None:
    if df.empty:
        st.info("No ETF composition data is available for this snapshot.")
        return

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config={
            "parent_etf": st.column_config.TextColumn("ETF"),
            "allocation_pct": st.column_config.NumberColumn("Allocation", format="%.2f%%"),
        },
    )


def render_breakdown_table(df: pd.DataFrame, label_column: str, height: int = 260) -> None:
    if df.empty:
        st.info("No matching rows for this selection.")
        return

    column_config = {
        label_column: st.column_config.TextColumn(label_column.replace("_", " ").title()),
        "parent_etf": st.column_config.TextColumn("ETF"),
        "contribution_pct": st.column_config.NumberColumn("Contribution", format="%.2f%%"),
    }
    if "underlying_weight_pct" in df.columns:
        column_config["underlying_weight_pct"] = st.column_config.NumberColumn(
            "Underlying weight",
            format="%.2f%%",
        )
    if "line_items" in df.columns:
        column_config["line_items"] = st.column_config.NumberColumn("Lines", format="%d")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config=column_config,
    )


available_dates = list_available_snapshot_dates()
if not available_dates:
    st.error("No complete PIE snapshots were found in ./data.")
    st.stop()

with st.sidebar:
    st.header("Controls")
    snapshot_date = st.selectbox("Snapshot date", options=available_dates, index=0)
    top_n = st.select_slider("Top N", options=[10, 20, 50], value=20)
    company_search = st.text_input("Search companies", placeholder="NVIDIA, Microsoft...")
    if st.button("Refresh analysis", use_container_width=True):
        load_report.clear()

report = load_report(snapshot_date)

st.markdown(
    f"""
    <div class="dashboard-banner">
      <h1>PIE Portfolio Look-Through Dashboard</h1>
      <p>Snapshot <strong>{report["snapshot_date"]}</strong> with drilldowns across companies, countries, sectors, and cross-ETF overlap.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

summary = report["summary"]
metrics = st.columns(5)
metrics[0].metric("Holdings rows", f'{summary["total_holdings_count"]:,}')
metrics[1].metric("Companies", f'{summary["unique_companies"]:,}')
metrics[2].metric("Countries", f'{summary["unique_countries"]:,}')
metrics[3].metric("Sectors", f'{summary["unique_sectors"]:,}')
metrics[4].metric("Portfolio total", f'{summary["portfolio_total_pct"]:.2f}%')

overview_tab, companies_tab, countries_tab, sectors_tab, overlap_tab, single_etf_tab = st.tabs(
    ["Overview", "Companies", "Countries", "Sectors", "Overlap", "Single ETF Analysis"]
)

with overview_tab:
    st.subheader("Portfolio Composition")
    st.caption("Fixed ETF allocation for the selected PIE snapshot.")
    composition_cols = st.columns([1.1, 0.9])
    with composition_cols[0]:
        render_pie_chart(report["etf_composition"], "parent_etf", "allocation_pct")
    with composition_cols[1]:
        render_etf_composition_table(report["etf_composition"])

    st.subheader("Top Exposures")
    overview_cols = st.columns(3)
    top_sections = [
        ("company_exposure", "company", "Top companies"),
        ("country_exposure", "country", "Top countries"),
        ("sector_exposure", "sector", "Top sectors"),
    ]
    for column, (report_key, label_column, title) in zip(overview_cols, top_sections):
        with column:
            render_bar_chart(report[report_key], label_column, title, top_n)
            render_exposure_table(report[report_key].head(top_n), label_column, height=320)

    st.subheader("Concentration Metrics")
    concentration = report["concentration_metrics"].copy()
    st.dataframe(
        concentration,
        use_container_width=True,
        hide_index=True,
        column_config={
            "dimension": st.column_config.TextColumn("Dimension"),
            "items": st.column_config.NumberColumn("Items", format="%d"),
            "top_10_pct": st.column_config.NumberColumn("Top 10", format="%.2f%%"),
            "top_20_pct": st.column_config.NumberColumn("Top 20", format="%.2f%%"),
            "top_50_pct": st.column_config.NumberColumn("Top 50", format="%.2f%%"),
            "hhi": st.column_config.NumberColumn("HHI", format="%.4f"),
            "effective_holdings": st.column_config.NumberColumn("Effective holdings", format="%.2f"),
        },
    )

with companies_tab:
    filtered_companies = filter_company_exposure(report["company_exposure"], company_search)
    st.subheader("Company exposure table")
    if company_search:
        st.caption(f'{len(filtered_companies):,} matches for "{company_search}"')
    render_exposure_table(filtered_companies, "company", height=520)

    company_cols = st.columns([1.4, 1.1])
    with company_cols[0]:
        render_bar_chart(filtered_companies, "company", f"Top {top_n} companies", top_n)
    with company_cols[1]:
        company_options = filtered_companies["company"].tolist() or report["company_exposure"]["company"].tolist()
        selected_company = st.selectbox("Company drilldown", options=company_options)
        company_drilldown = get_company_drilldown(report["company_etf_breakdown"], selected_company)
        render_breakdown_table(company_drilldown, "company", height=340)

with countries_tab:
    st.subheader("Country exposure")
    country_cols = st.columns([1.35, 1])
    with country_cols[0]:
        render_bar_chart(report["country_exposure"], "country", f"Top {top_n} countries", top_n)
    with country_cols[1]:
        render_exposure_table(report["country_exposure"], "country", height=460)

    selected_country = st.selectbox("Country drilldown", options=report["country_exposure"]["country"].tolist())
    country_drilldown = get_dimension_drilldown(
        report["country_etf_breakdown"],
        report["country_company_drivers"],
        "country",
        selected_country,
    )
    drilldown_cols = st.columns(2)
    with drilldown_cols[0]:
        st.caption("Contribution by ETF")
        render_breakdown_table(country_drilldown["etf_breakdown"], "country", height=280)
    with drilldown_cols[1]:
        st.caption("Top companies driving this country")
        render_exposure_table(country_drilldown["top_companies"].head(top_n), "company", height=280)

with sectors_tab:
    st.subheader("Sector exposure")
    sector_cols = st.columns([1.35, 1])
    with sector_cols[0]:
        render_bar_chart(report["sector_exposure"], "sector", f"Top {top_n} sectors", top_n)
    with sector_cols[1]:
        render_exposure_table(report["sector_exposure"], "sector", height=460)

    selected_sector = st.selectbox("Sector drilldown", options=report["sector_exposure"]["sector"].tolist())
    sector_drilldown = get_dimension_drilldown(
        report["sector_etf_breakdown"],
        report["sector_company_drivers"],
        "sector",
        selected_sector,
    )
    drilldown_cols = st.columns(2)
    with drilldown_cols[0]:
        st.caption("Contribution by ETF")
        render_breakdown_table(sector_drilldown["etf_breakdown"], "sector", height=280)
    with drilldown_cols[1]:
        st.caption("Top companies driving this sector")
        render_exposure_table(sector_drilldown["top_companies"].head(top_n), "company", height=280)

with overlap_tab:
    overlap_table = report["overlap_table"].copy()
    st.subheader("Cross-ETF overlap")
    st.caption("Overlap weights are portfolio contribution percentage points, not raw ETF holding weights.")

    overlap_metrics = st.columns(3)
    overlap_metrics[0].metric("Overlapping companies", f'{len(overlap_table):,}')
    if overlap_table.empty:
        overlap_metrics[1].metric("Highest overlap", "0.00%")
        overlap_metrics[2].metric("Max ETF count", "0")
        st.info("No companies are currently held by more than one ETF.")
    else:
        top_overlap = overlap_table.iloc[0]
        overlap_metrics[1].metric(
            "Highest overlap",
            f'{top_overlap["total_contribution_pct"]:.2f}%',
            top_overlap["company"],
        )
        overlap_metrics[2].metric("Max ETF count", f'{int(overlap_table["num_etfs"].max())}')
        render_bar_chart(
            overlap_table.rename(columns={"total_contribution_pct": "contribution_pct"}),
            "company",
            f"Top {top_n} overlapping companies",
            top_n,
        )
        display_overlap = overlap_table.copy()
        overlap_column_config = {
            "company": st.column_config.TextColumn("Company"),
            "total_contribution_pct": st.column_config.NumberColumn("Total overlap", format="%.2f%%"),
            "num_etfs": st.column_config.NumberColumn("ETF count", format="%d"),
            "etfs": st.column_config.TextColumn("ETFs"),
        }
        for column in display_overlap.columns:
            if column not in overlap_column_config and column not in {"company", "etfs"}:
                overlap_column_config[column] = st.column_config.NumberColumn(column, format="%.2f%%")
        st.dataframe(
            display_overlap,
            use_container_width=True,
            hide_index=True,
            height=520,
            column_config=overlap_column_config,
        )

with single_etf_tab:
    st.subheader("Single ETF Analysis")
    st.caption("Inspect ETF-internal weights across companies, countries, and sectors.")

    selected_etf = st.selectbox("Select ETF", options=report["single_etf_options"])
    etf_report = report["single_etf_analysis"].get(selected_etf, {})
    sections = [
        ("Top companies", "company", "company_exposure"),
        ("Top countries", "country", "country_exposure"),
        ("Top sectors", "sector", "sector_exposure"),
    ]

    for section_title, label_column, data_key in sections:
        section_data = etf_report.get(data_key, pd.DataFrame(columns=[label_column, "weight_pct"]))
        st.subheader(f"{selected_etf} {section_title}")
        section_cols = st.columns([1.35, 1])
        with section_cols[0]:
            render_bar_chart(
                section_data.rename(columns={"weight_pct": "contribution_pct"}),
                label_column,
                f"{selected_etf} {section_title}",
                top_n,
            )
        with section_cols[1]:
            render_weight_table(section_data.head(top_n), label_column, height=360)
