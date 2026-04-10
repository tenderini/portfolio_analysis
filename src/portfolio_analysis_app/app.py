from __future__ import annotations

from html import escape
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import streamlit as st

if __package__ in {None, ""}:
    # Streamlit Cloud can execute this file directly instead of importing it as a package module.
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from src.portfolio_analysis_app.app_config import load_app_config
    from src.portfolio_analysis_app.app_theme import (
        BAR_COLOR_SCALE,
        DARK_ETF_COLOR_MAP,
        TEXT_PRIMARY,
        apply_dark_figure_layout,
        build_bar_value_axis_range,
        build_theme_css,
    )
    from src.portfolio_analysis_app.dashboard_metrics import build_summary_metrics
    from src.portfolio_analysis_app.custom_portfolios import (
        DEFAULT_PORTFOLIO_NAME,
        build_combined_holdings_for_portfolio,
        load_saved_portfolios,
        refresh_supported_etf_snapshot,
        resolve_portfolio_entries,
        save_saved_portfolios,
        validate_portfolio_entries,
    )
    from src.portfolio_analysis_app.etf_catalog import (
        build_catalog_dataframe,
        load_etf_catalog,
        search_etf_catalog,
    )
    from src.portfolio_analysis_app.portfolio_analysis import (
        build_report_from_holdings,
        filter_company_exposure,
        format_snapshot_date,
        get_company_drilldown,
        get_dimension_drilldown,
    )
else:
    from .app_config import load_app_config
    from .app_theme import (
        BAR_COLOR_SCALE,
        DARK_ETF_COLOR_MAP,
        TEXT_PRIMARY,
        apply_dark_figure_layout,
        build_bar_value_axis_range,
        build_theme_css,
    )
    from .dashboard_metrics import build_summary_metrics
    from .custom_portfolios import (
        DEFAULT_PORTFOLIO_NAME,
        build_combined_holdings_for_portfolio,
        load_saved_portfolios,
        refresh_supported_etf_snapshot,
        resolve_portfolio_entries,
        save_saved_portfolios,
        validate_portfolio_entries,
    )
    from .etf_catalog import (
        build_catalog_dataframe,
        load_etf_catalog,
        search_etf_catalog,
    )
    from .portfolio_analysis import (
        build_report_from_holdings,
        filter_company_exposure,
        format_snapshot_date,
        get_company_drilldown,
        get_dimension_drilldown,
    )

try:
    import plotly.express as px
except ImportError:  # pragma: no cover - optional dependency
    px = None


PLOTLY_STATIC_CONFIG = {"staticPlot": True, "displayModeBar": False}


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
        color_continuous_scale=BAR_COLOR_SCALE,
        title=title,
    )
    fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside", cliponaxis=False)
    apply_dark_figure_layout(
        fig,
        title,
        max(420, top_n * 28),
    )
    fig.update_layout(
        coloraxis_showscale=False,
        xaxis_title="Portfolio weight (%)",
        yaxis_title="",
        xaxis=dict(
            range=build_bar_value_axis_range(chart_data["contribution_pct"]),
            gridcolor="rgba(138, 160, 181, 0.18)",
            zeroline=False,
        ),
        hoverlabel=dict(bgcolor="#0b131c", font_color=TEXT_PRIMARY, bordercolor="rgba(78, 205, 196, 0.28)"),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_STATIC_CONFIG)


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
        color_discrete_map=DARK_ETF_COLOR_MAP,
    )
    fig.update_traces(
        textposition="inside",
        texttemplate="%{label}<br>%{value:.1f}%",
        hovertemplate="%{label}: %{value:.2f}%<extra></extra>",
        sort=False,
    )
    apply_dark_figure_layout(fig, title, 360)
    fig.update_layout(
        showlegend=True,
        margin=dict(l=0, r=0, t=56 if title else 12, b=12),
        legend=dict(
            bgcolor="rgba(0, 0, 0, 0)",
            font=dict(color=TEXT_PRIMARY),
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_STATIC_CONFIG)


def render_exposure_table(df: pd.DataFrame, label_column: str, height: int = 420) -> None:
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config={
            label_column: st.column_config.TextColumn(label_column.replace("_", " ").title()),
            "contribution_pct": st.column_config.NumberColumn(
                "Portfolio weight",
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


def render_etf_description_cards(descriptions: list[dict[str, str]]) -> None:
    if not descriptions:
        return

    columns = st.columns(len(descriptions))
    for column, item in zip(columns, descriptions):
        ticker = str(item.get("ticker", "ETF"))
        accent = DARK_ETF_COLOR_MAP.get(ticker, "#4ecdc4")
        description = escape(str(item.get("description", "")))
        role = escape(str(item.get("role", "")))
        with column:
            st.markdown(
                f"""
                <div class="etf-description-card" style="--etf-accent: {escape(accent)};">
                  <div class="etf-description-ticker">{escape(ticker)}</div>
                  <p class="etf-description-body">{description}</p>
                  <p class="etf-description-role">{role}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_breakdown_table(
    df: pd.DataFrame,
    label_column: str,
    height: int = 260,
    show_holdings_count: bool = True,
) -> None:
    if df.empty:
        st.info("No matching rows for this selection.")
        return

    column_config = {
        label_column: st.column_config.TextColumn(label_column.replace("_", " ").title()),
        "parent_etf": st.column_config.TextColumn("ETF"),
        "contribution_pct": st.column_config.NumberColumn("Portfolio weight", format="%.2f%%"),
    }
    if "underlying_weight_pct" in df.columns:
        column_config["underlying_weight_pct"] = st.column_config.NumberColumn(
            "ETF weight",
            format="%.2f%%",
        )
    if "line_items" in df.columns and show_holdings_count:
        column_config["line_items"] = st.column_config.NumberColumn("Holdings count", format="%d")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config=column_config,
    )


def render_cash_equivalent_table(df: pd.DataFrame, height: int = 320) -> None:
    if df.empty:
        st.info("No cash-equivalent holdings were identified for this snapshot.")
        return

    visible_columns = [
        "company",
        "parent_etf",
        "country",
        "sector",
        "asset_class",
        "holding_type",
        "weight_pct",
        "contribution_pct",
    ]
    available_columns = [column for column in visible_columns if column in df.columns]
    st.dataframe(
        df[available_columns],
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config={
            "company": st.column_config.TextColumn("Holding"),
            "parent_etf": st.column_config.TextColumn("ETF"),
            "country": st.column_config.TextColumn("Country"),
            "sector": st.column_config.TextColumn("Sector"),
            "asset_class": st.column_config.TextColumn("Asset class"),
            "holding_type": st.column_config.TextColumn("Classification"),
            "weight_pct": st.column_config.NumberColumn("ETF weight", format="%.2f%%"),
            "contribution_pct": st.column_config.NumberColumn("Portfolio weight", format="%.2f%%"),
        },
    )


def _normalise_portfolio_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entries:
        return [{"etf_id": "", "weight_pct": 0.0, "search_text": ""}]

    normalised_entries = []
    for entry in entries:
        normalised_entries.append(
            {
                "etf_id": str(entry.get("etf_id", "")),
                "weight_pct": float(entry.get("weight_pct", 0.0) or 0.0),
                "search_text": str(entry.get("search_text", "")),
            }
        )
    return normalised_entries


def _set_portfolio_editor_state(portfolio: dict[str, Any]) -> None:
    st.session_state["selected_portfolio_name"] = str(portfolio.get("name", DEFAULT_PORTFOLIO_NAME))
    st.session_state["portfolio_editor_name"] = str(portfolio.get("name", DEFAULT_PORTFOLIO_NAME))
    st.session_state["portfolio_editor_entries"] = _normalise_portfolio_entries(
        list(portfolio.get("entries", []))
    )


def _upsert_saved_portfolio(
    saved_portfolios: list[dict[str, Any]],
    portfolio_name: str,
    entries: list[dict[str, Any]],
    selected_name: str,
) -> list[dict[str, Any]]:
    cleaned_name = portfolio_name.strip() or selected_name or DEFAULT_PORTFOLIO_NAME
    updated_portfolio = {
        "name": cleaned_name,
        "entries": _normalise_portfolio_entries(entries),
    }

    updated_portfolios: list[dict[str, Any]] = []
    replaced = False
    for portfolio in saved_portfolios:
        if str(portfolio.get("name")) == selected_name:
            updated_portfolios.append(updated_portfolio)
            replaced = True
            continue

        if str(portfolio.get("name")) == cleaned_name and cleaned_name != selected_name:
            raise ValueError(f'A saved portfolio named "{cleaned_name}" already exists.')
        updated_portfolios.append(portfolio)

    if not replaced:
        updated_portfolios.append(updated_portfolio)
    return updated_portfolios


def _render_catalogue_match_picker(
    row_index: int,
    entry: dict[str, Any],
    catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    search_text = st.text_input(
        f"Search ETF {row_index}",
        value=str(entry.get("search_text", "")),
    )
    matches = search_etf_catalog(search_text, catalog)
    labels = ["Select ETF..."] + [
        f'{match["symbol"]} · {match["isin"]} · {match["display_name"]}'
        for match in matches
    ]
    label_to_id = {"Select ETF...": ""}
    label_to_id.update(
        {
            f'{match["symbol"]} · {match["isin"]} · {match["display_name"]}': match["etf_id"]
            for match in matches
        }
    )
    current_id = str(entry.get("etf_id", ""))
    current_label = next(
        (label for label, etf_id in label_to_id.items() if etf_id == current_id),
        labels[0],
    )
    selected_label = st.selectbox(
        f"Match {row_index}",
        options=labels,
        index=labels.index(current_label),
    )
    return {
        "etf_id": label_to_id[selected_label],
        "weight_pct": float(entry.get("weight_pct", 0.0) or 0.0),
        "search_text": search_text,
    }


def _render_portfolio_builder(
    saved_portfolios: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    if not saved_portfolios:
        st.error("No saved portfolios are available.")
        st.stop()

    portfolios_by_name = {str(portfolio["name"]): portfolio for portfolio in saved_portfolios}
    if (
        "selected_portfolio_name" not in st.session_state
        or st.session_state["selected_portfolio_name"] not in portfolios_by_name
    ):
        _set_portfolio_editor_state(saved_portfolios[0])

    portfolio_names = list(portfolios_by_name)
    current_name = str(st.session_state["selected_portfolio_name"])
    current_index = portfolio_names.index(current_name)

    with st.expander("Portfolio Builder", expanded=True):
        selected_name = st.selectbox("Saved portfolio", options=portfolio_names, index=current_index)
        if selected_name != current_name:
            _set_portfolio_editor_state(portfolios_by_name[selected_name])
            current_name = selected_name

        portfolio_name = st.text_input(
            "Portfolio name",
            value=str(st.session_state.get("portfolio_editor_name", current_name)),
        )
        st.session_state["portfolio_editor_name"] = portfolio_name

        editor_entries = _normalise_portfolio_entries(
            list(st.session_state.get("portfolio_editor_entries", []))
        )
        if st.button("Add ETF"):
            editor_entries.append({"etf_id": "", "weight_pct": 0.0, "search_text": ""})

        rendered_entries: list[dict[str, Any]] = []
        remove_index: int | None = None
        for index, entry in enumerate(editor_entries, start=1):
            row_columns = st.columns([1.7, 1.6, 1.0, 0.8])
            with row_columns[0]:
                rendered_entry = _render_catalogue_match_picker(index, entry, catalog)
            with row_columns[1]:
                weight_pct = st.number_input(
                    f"Weight {index}",
                    value=float(entry.get("weight_pct", 0.0) or 0.0),
                    min_value=0.0,
                    step=0.5,
                    format="%.2f",
                )
            with row_columns[2]:
                if len(editor_entries) > 1 and st.button(f"Remove ETF {index}"):
                    remove_index = index - 1
            rendered_entry["weight_pct"] = weight_pct
            rendered_entries.append(rendered_entry)

        if remove_index is not None:
            rendered_entries.pop(remove_index)

        st.session_state["portfolio_editor_entries"] = _normalise_portfolio_entries(rendered_entries)

        if st.button("Save portfolio"):
            try:
                updated_portfolios = _upsert_saved_portfolio(
                    saved_portfolios=saved_portfolios,
                    portfolio_name=portfolio_name,
                    entries=rendered_entries,
                    selected_name=current_name,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                save_saved_portfolios(updated_portfolios)
                _set_portfolio_editor_state(
                    next(
                        portfolio
                        for portfolio in updated_portfolios
                        if portfolio["name"] == (portfolio_name.strip() or current_name or DEFAULT_PORTFOLIO_NAME)
                    )
                )
                saved_portfolios[:] = updated_portfolios
                portfolios_by_name = {str(portfolio["name"]): portfolio for portfolio in saved_portfolios}
                st.success("Portfolio saved.")

        resolved_entries = resolve_portfolio_entries(st.session_state["portfolio_editor_entries"])
        validation = validate_portfolio_entries(st.session_state["portfolio_editor_entries"])

        for entry in resolved_entries:
            etf_id = str(entry.get("etf_id", "")).strip()
            search_text = str(entry.get("search_text", "")).strip()
            if not etf_id and not search_text:
                continue
            if entry.get("error"):
                label = search_text or etf_id
                st.markdown(f'Invalid ETF: `{escape(label)}`. {escape(str(entry["error"]))}')
                continue

            st.markdown(
                f'`{escape(str(entry["symbol"]))}` · {escape(str(entry["isin"]))} · {escape(str(entry["display_name"]))}'
            )
            if st.button(f'Refresh {entry["symbol"]}'):
                try:
                    refresh_supported_etf_snapshot(entry)
                except Exception as exc:  # pragma: no cover - runtime/network path
                    st.error(str(exc))
                else:  # pragma: no cover - runtime/network path
                    st.success(f'Refreshed cached holdings for {entry["symbol"]}.')

        return {
            "portfolio_name": portfolio_name.strip() or current_name or DEFAULT_PORTFOLIO_NAME,
            "entries": st.session_state["portfolio_editor_entries"],
            "resolved_entries": resolved_entries,
            "validation": validation,
        }


def main() -> None:
    app_config = load_app_config()

    st.set_page_config(
        page_title=app_config.content.page_title,
        layout="wide",
    )
    st.markdown(build_theme_css(), unsafe_allow_html=True)
    top_n = app_config.ui.top_n
    company_search = ""
    catalog = load_etf_catalog()
    saved_portfolios = load_saved_portfolios()
    builder_state = _render_portfolio_builder(saved_portfolios, catalog)

    if not builder_state["validation"]["is_valid"]:
        for error in builder_state["validation"]["errors"]:
            st.markdown(escape(error))
        st.stop()

    try:
        portfolio_inputs = build_combined_holdings_for_portfolio(builder_state["entries"])
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    report = build_report_from_holdings(
        combined_holdings=portfolio_inputs["combined_holdings"],
        snapshot_label=portfolio_inputs["snapshot_label"],
        etf_descriptions=portfolio_inputs["etf_descriptions"],
    )
    display_snapshot_date = format_snapshot_date(report["snapshot_date"])

    st.markdown(
        f"""
        <div class="dashboard-banner">
          <h1>{app_config.content.dashboard_title}</h1>
          <p>{escape(builder_state["portfolio_name"])} · {app_config.content.snapshot_description_template.format(snapshot_date=display_snapshot_date)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    summary = report["summary"]
    headline_metrics = build_summary_metrics(summary)
    if not app_config.ui.show_portfolio_total_in_overview:
        headline_metrics = [
            metric for metric in headline_metrics if metric["label"] != "Portfolio total"
        ]
    metric_columns = st.columns(len(headline_metrics))
    for column, metric in zip(metric_columns, headline_metrics):
        column.metric(metric["label"], metric["value"])

    overview_tab, companies_tab, geography_tab, sectors_tab, overlap_tab, single_etf_tab, catalogue_tab = st.tabs(
        ["Overview", "Companies", "Countries/Continents", "Sectors", "Overlap", "Single ETF Analysis", "ETF Catalogue"]
    )

    with overview_tab:
        st.subheader("Portfolio Composition")
        st.caption("Current ETF allocation for the selected saved portfolio.")
        render_etf_description_cards(report["etf_descriptions"])
        st.markdown('<div class="etf-description-spacer"></div>', unsafe_allow_html=True)
        composition_cols = st.columns([1.1, 0.9])
        with composition_cols[0]:
            render_pie_chart(report["etf_composition"], "parent_etf", "allocation_pct")
        with composition_cols[1]:
            render_etf_composition_table(report["etf_composition"])

        st.subheader("Top Exposures")
        top_sections = [
            ("company_exposure", "company", "Top companies"),
            ("country_exposure", "country", "Top countries"),
            ("sector_exposure", "sector", "Top sectors"),
            ("continent_exposure", "continent", "Top continents"),
        ]
        for row_start in range(0, len(top_sections), 2):
            overview_cols = st.columns(2)
            row_sections = top_sections[row_start : row_start + 2]
            for column, (report_key, label_column, title) in zip(overview_cols, row_sections):
                with column:
                    render_bar_chart(report[report_key], label_column, title, top_n)

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

        with st.expander("Cash-equivalent details", expanded=False):
            st.caption(
                "Cash-equivalents are liquidity, collateral, or derivative-support positions held by the ETF. "
                "They are kept in the snapshot, but excluded from company overlap and company exposure analytics."
            )
            cash_equivalent = report["cash_equivalent_holdings"].copy()
            cash_metrics = st.columns(3)
            cash_metrics[0].metric("Cash-equivalent rows", f'{summary["cash_equivalent_rows"]:,}')
            cash_metrics[1].metric("Unique labels", f'{summary["cash_equivalent_unique_labels"]:,}')
            cash_metrics[2].metric("Portfolio weight", f'{summary["cash_equivalent_total_pct"]:.2f}%')
            render_cash_equivalent_table(cash_equivalent, height=320)

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

    with geography_tab:
        countries_tab, continents_tab = st.tabs(["Countries", "Continents"])

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

        with continents_tab:
            st.subheader("Continent exposure")
            continent_cols = st.columns([1.35, 1])
            with continent_cols[0]:
                render_bar_chart(report["continent_exposure"], "continent", f"Top {top_n} continents", top_n)
            with continent_cols[1]:
                render_exposure_table(report["continent_exposure"], "continent", height=460)

            selected_continent = st.selectbox(
                "Continent drilldown",
                options=report["continent_exposure"]["continent"].tolist(),
            )
            continent_drilldown = get_dimension_drilldown(
                report["continent_etf_breakdown"],
                report["continent_company_drivers"],
                "continent",
                selected_continent,
            )
            drilldown_cols = st.columns(2)
            with drilldown_cols[0]:
                st.caption("Contribution by ETF")
                render_breakdown_table(continent_drilldown["etf_breakdown"], "continent", height=280)
            with drilldown_cols[1]:
                st.caption("Top companies driving this continent")
                render_exposure_table(continent_drilldown["top_companies"].head(top_n), "company", height=280)

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
        st.caption("Inspect ETF-internal weights across companies, countries, sectors, and continents.")

        selected_etf = st.selectbox("Select ETF", options=report["single_etf_options"])
        etf_report = report["single_etf_analysis"].get(selected_etf, {})
        single_etf_metrics = st.columns(3)
        single_etf_metrics[0].metric("Companies", f'{len(etf_report.get("company_exposure", [])):,}')
        single_etf_metrics[1].metric("Countries", f'{len(etf_report.get("country_exposure", [])):,}')
        single_etf_metrics[2].metric("Sectors", f'{len(etf_report.get("sector_exposure", [])):,}')
        sections = [
            ("Top companies", "company", "company_exposure"),
            ("Top countries", "country", "country_exposure"),
            ("Top sectors", "sector", "sector_exposure"),
            ("Top continents", "continent", "continent_exposure"),
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
                render_weight_table(section_data, label_column, height=360)

    with catalogue_tab:
        st.subheader("Supported ETF Catalogue")
        catalogue_search = st.text_input("Catalogue search", value="")
        catalogue_df = build_catalog_dataframe(
            search_etf_catalog(catalogue_search, catalog),
            data_dir=Path("data"),
        )
        st.dataframe(
            catalogue_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "symbol": st.column_config.TextColumn("Ticker"),
                "isin": st.column_config.TextColumn("ISIN"),
                "display_name": st.column_config.TextColumn("ETF"),
                "asset_class": st.column_config.TextColumn("Asset class"),
                "cached_snapshot": st.column_config.TextColumn("Cached snapshot"),
            },
        )


if __name__ == "__main__":
    main()
