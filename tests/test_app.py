import importlib.util
import sys
import types
import unittest
from pathlib import Path

import pandas as pd


class DummyContext:
    def __init__(self, parent=None):
        self.parent = parent

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def metric(self, *args, **kwargs):
        if self.parent is not None and args:
            self.parent.metric_calls.append(args)
        return None


class FakeColumnConfig:
    @staticmethod
    def TextColumn(*args, **kwargs):
        return {"args": args, "kwargs": kwargs}

    @staticmethod
    def NumberColumn(*args, **kwargs):
        return {"args": args, "kwargs": kwargs}


class FakeStreamlit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.sidebar_enter_count = 0
        self.control_labels: list[str] = []
        self.tab_labels: list[list[str]] = []
        self.metric_calls: list[tuple] = []
        self.page_config_calls: list[dict] = []
        self.markdown_calls: list[str] = []
        self.dataframe_calls: list[dict] = []
        self.bar_titles: list[str | None] = []
        self.bar_figures: list["FakeFigure"] = []
        self.column_config = FakeColumnConfig()
        self.sidebar = self._Sidebar(self)

    class _Sidebar(DummyContext):
        def __init__(self, parent: "FakeStreamlit") -> None:
            self.parent = parent

        def __enter__(self):
            self.parent.sidebar_enter_count += 1
            return self

    def cache_data(self, **kwargs):
        def decorator(func):
            func.clear = lambda: None
            return func

        return decorator

    def set_page_config(self, **kwargs):
        self.page_config_calls.append(kwargs)
        return None

    def markdown(self, *args, **kwargs):
        if args:
            self.markdown_calls.append(args[0])
        return None

    def info(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def stop(self):
        raise RuntimeError("streamlit stop called unexpectedly")

    def header(self, *args, **kwargs):
        return None

    def subheader(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def dataframe(self, data=None, *args, **kwargs):
        self.dataframe_calls.append({"data": data, "kwargs": kwargs})
        return None

    def bar_chart(self, *args, **kwargs):
        return None

    def plotly_chart(self, *args, **kwargs):
        return None

    def columns(self, count_or_widths):
        count = count_or_widths if isinstance(count_or_widths, int) else len(count_or_widths)
        return [DummyContext(self) for _ in range(count)]

    def tabs(self, labels):
        self.tab_labels.append(list(labels))
        return [DummyContext() for _ in labels]

    def expander(self, *args, **kwargs):
        return DummyContext()

    def selectbox(self, label, options, index=0, format_func=None):
        self.control_labels.append(label)
        return list(options)[index]

    def select_slider(self, label, options, value=None):
        self.control_labels.append(label)
        return value if value is not None else list(options)[0]

    def text_input(self, label, placeholder=None):
        self.control_labels.append(label)
        return ""

    def button(self, label, **kwargs):
        self.control_labels.append(label)
        return False


class FakeFigure:
    def __init__(self) -> None:
        self.updated_layout: dict = {}

    def update_traces(self, *args, **kwargs):
        return self

    def update_layout(self, *args, **kwargs):
        self.updated_layout.update(kwargs)
        return self


def build_fake_report() -> dict:
    single_etf_company_exposure = pd.DataFrame(
        {
            "company": [f"Company {index}" for index in range(1, 26)],
            "weight_pct": [float(index) for index in range(25, 0, -1)],
        }
    )
    company_exposure = pd.DataFrame(
        {"company": ["Apple", "Microsoft"], "contribution_pct": [4.0, 3.0]}
    )
    country_exposure = pd.DataFrame(
        {"country": ["US", "JP"], "contribution_pct": [60.0, 8.0]}
    )
    sector_exposure = pd.DataFrame(
        {"sector": ["Technology", "Financials"], "contribution_pct": [25.0, 12.0]}
    )
    breakdown = pd.DataFrame(
        {
            "company": ["Apple"],
            "country": ["US"],
            "sector": ["Technology"],
            "parent_etf": ["SWDA"],
            "contribution_pct": [4.0],
            "underlying_weight_pct": [5.0],
            "line_items": [1],
        }
    )
    return {
        "snapshot_date": "20260408",
        "summary": {
            "unique_companies": 2,
            "unique_countries": 2,
            "unique_sectors": 2,
            "portfolio_total_pct": 100.0,
            "cash_equivalent_rows": 1,
            "cash_equivalent_unique_labels": 1,
            "cash_equivalent_total_pct": 0.4,
        },
        "etf_descriptions": [
            {"ticker": "SWDA", "description": "Developed markets", "role": "Core exposure"},
            {"ticker": "EMIM", "description": "Emerging markets", "role": "Emerging exposure"},
            {"ticker": "WSML", "description": "Small cap", "role": "Small cap exposure"},
        ],
        "etf_composition": pd.DataFrame(
            {
                "parent_etf": ["SWDA", "EMIM", "WSML"],
                "allocation_pct": [78.0, 12.0, 10.0],
            }
        ),
        "company_exposure": company_exposure,
        "country_exposure": country_exposure,
        "continent_exposure": pd.DataFrame(
            {
                "continent": ["North America", "Asia", "Europe"],
                "contribution_pct": [63.0, 5.0, 4.0],
            }
        ),
        "sector_exposure": sector_exposure,
        "concentration_metrics": pd.DataFrame(
            {
                "dimension": ["Company"],
                "items": [2],
                "top_10_pct": [7.0],
                "top_20_pct": [7.0],
                "top_50_pct": [7.0],
                "hhi": [0.0025],
                "effective_holdings": [400.0],
            }
        ),
        "cash_equivalent_holdings": pd.DataFrame(
            [
                {
                    "company": "USD CASH",
                    "parent_etf": "SWDA",
                    "country": "US",
                    "sector": "Cash and/or Derivatives",
                    "asset_class": "Cash",
                    "holding_type": "Cash",
                    "weight_pct": 0.5,
                    "contribution_pct": 0.4,
                }
            ]
        ),
        "company_etf_breakdown": breakdown[["company", "parent_etf", "contribution_pct", "underlying_weight_pct", "line_items"]],
        "country_etf_breakdown": breakdown[["country", "parent_etf", "contribution_pct", "underlying_weight_pct", "line_items"]],
        "country_company_drivers": breakdown[["country", "company", "contribution_pct"]],
        "continent_etf_breakdown": pd.DataFrame(
            {
                "continent": ["North America"],
                "parent_etf": ["SWDA"],
                "contribution_pct": [63.0],
                "underlying_weight_pct": [65.0],
                "line_items": [2],
            }
        ),
        "continent_company_drivers": pd.DataFrame(
            {
                "continent": ["North America", "North America"],
                "company": ["Apple", "Microsoft"],
                "contribution_pct": [4.0, 3.0],
            }
        ),
        "sector_etf_breakdown": breakdown[["sector", "parent_etf", "contribution_pct", "underlying_weight_pct", "line_items"]],
        "sector_company_drivers": breakdown[["sector", "company", "contribution_pct"]],
        "overlap_table": pd.DataFrame(columns=["company", "total_contribution_pct", "num_etfs", "etfs"]),
        "single_etf_options": ["SWDA"],
        "single_etf_analysis": {
            "SWDA": {
                "company_exposure": single_etf_company_exposure,
                "country_exposure": pd.DataFrame(
                    {"country": ["US", "JP", "DE"], "weight_pct": [60.0, 25.0, 15.0]}
                ),
                "sector_exposure": pd.DataFrame(
                    {"sector": ["Technology", "Financials"], "weight_pct": [70.0, 30.0]}
                ),
                "continent_exposure": pd.DataFrame(
                    {"continent": ["North America", "Europe"], "weight_pct": [75.0, 25.0]}
                ),
            }
        },
    }


class AppLayoutTests(unittest.TestCase):
    def load_app(
        self,
        *,
        fake_metrics=None,
        fake_config=None,
    ) -> FakeStreamlit:
        fake_streamlit = FakeStreamlit()
        fake_theme = types.SimpleNamespace(
            BAR_COLOR_SCALE=[],
            DARK_ETF_COLOR_MAP={},
            TEXT_PRIMARY="#fff",
            apply_dark_figure_layout=lambda fig, title=None, height=None: fig,
            build_bar_value_axis_range=lambda values: [0.0, 1.0],
            build_theme_css=lambda: "<style></style>",
        )
        fake_metrics = fake_metrics or types.SimpleNamespace(
            build_summary_metrics=lambda summary: [{"label": "Companies", "value": "2"}]
        )
        fake_config = fake_config or types.SimpleNamespace(
            load_app_config=lambda: types.SimpleNamespace(
                ui=types.SimpleNamespace(show_portfolio_total_in_overview=False, top_n=20),
                content=types.SimpleNamespace(
                    page_title="PIE Portfolio Analysis",
                    dashboard_title="PIE Portfolio Look-Through Dashboard",
                    snapshot_description_template=(
                        "Snapshot <strong>{snapshot_date}</strong> with drilldowns across companies, "
                        "countries, sectors, and cross-ETF overlap."
                    ),
                ),
            )
        )
        fake_portfolio = types.SimpleNamespace(
            build_report=lambda snapshot_date=None: build_fake_report(),
            filter_company_exposure=lambda df, search_text="": df,
            format_snapshot_date=lambda snapshot_date: snapshot_date,
            get_company_drilldown=lambda df, company: df,
            get_dimension_drilldown=lambda etf_breakdown, company_drivers, dimension, value: {
                "etf_breakdown": etf_breakdown,
                "top_companies": company_drivers,
            },
            list_available_snapshot_dates=lambda: ["20260408", "20260314"],
        )

        def fake_bar(*args, **kwargs):
            fake_streamlit.bar_titles.append(kwargs.get("title"))
            figure = FakeFigure()
            fake_streamlit.bar_figures.append(figure)
            return figure

        fake_plotly = types.ModuleType("plotly")
        fake_plotly_express = types.SimpleNamespace(
            bar=fake_bar,
            pie=lambda *args, **kwargs: FakeFigure(),
        )
        previous_modules = {
            name: sys.modules.get(name)
            for name in [
                "streamlit",
                "src.portfolio_analysis_app.app",
                "src.portfolio_analysis_app.app_config",
                "src.portfolio_analysis_app.app_theme",
                "src.portfolio_analysis_app.dashboard_metrics",
                "src.portfolio_analysis_app.portfolio_analysis",
                "plotly",
                "plotly.express",
            ]
        }
        sys.modules["streamlit"] = fake_streamlit
        sys.modules.pop("src.portfolio_analysis_app.app", None)
        sys.modules["src.portfolio_analysis_app.app_config"] = fake_config
        sys.modules["src.portfolio_analysis_app.app_theme"] = fake_theme
        sys.modules["src.portfolio_analysis_app.dashboard_metrics"] = fake_metrics
        sys.modules["src.portfolio_analysis_app.portfolio_analysis"] = fake_portfolio
        sys.modules["plotly"] = fake_plotly
        sys.modules["plotly.express"] = fake_plotly_express

        try:
            spec = importlib.util.spec_from_file_location("test_app_module", Path("app.py"))
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        finally:
            for name, previous_module in previous_modules.items():
                if previous_module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous_module

        return fake_streamlit

    def test_app_uses_fixed_defaults_without_sidebar_controls(self) -> None:
        fake_streamlit = self.load_app()

        self.assertEqual(fake_streamlit.sidebar_enter_count, 0)
        self.assertNotIn("Top N", fake_streamlit.control_labels)
        self.assertNotIn("Search companies", fake_streamlit.control_labels)
        self.assertNotIn("Refresh analysis", fake_streamlit.control_labels)
        self.assertIn(
            ["Overview", "Companies", "Countries/Continents", "Sectors", "Overlap", "Single ETF Analysis"],
            fake_streamlit.tab_labels,
        )
        self.assertIn(["Countries", "Continents"], fake_streamlit.tab_labels)

    def test_app_hides_portfolio_total_metric_by_default(self) -> None:
        fake_metrics = types.SimpleNamespace(
            build_summary_metrics=lambda summary: [
                {"label": "Companies", "value": "2"},
                {"label": "Portfolio total", "value": "99.92%"},
            ]
        )

        fake_streamlit = self.load_app(fake_metrics=fake_metrics)

        self.assertIn(("Companies", "2"), fake_streamlit.metric_calls)
        self.assertNotIn(("Portfolio total", "99.92%"), fake_streamlit.metric_calls)

    def test_app_can_show_portfolio_total_metric_from_config(self) -> None:
        fake_metrics = types.SimpleNamespace(
            build_summary_metrics=lambda summary: [
                {"label": "Companies", "value": "2"},
                {"label": "Portfolio total", "value": "99.92%"},
            ]
        )
        fake_config = types.SimpleNamespace(
            load_app_config=lambda: types.SimpleNamespace(
                ui=types.SimpleNamespace(show_portfolio_total_in_overview=True, top_n=20),
                content=types.SimpleNamespace(
                    page_title="PIE Portfolio Analysis",
                    dashboard_title="PIE Portfolio Look-Through Dashboard",
                    snapshot_description_template="Snapshot <strong>{snapshot_date}</strong>",
                ),
            )
        )

        fake_streamlit = self.load_app(fake_metrics=fake_metrics, fake_config=fake_config)

        self.assertIn(("Portfolio total", "99.92%"), fake_streamlit.metric_calls)

    def test_app_uses_configured_content_defaults(self) -> None:
        fake_config = types.SimpleNamespace(
            load_app_config=lambda: types.SimpleNamespace(
                ui=types.SimpleNamespace(show_portfolio_total_in_overview=False, top_n=7),
                content=types.SimpleNamespace(
                    page_title="Configured Title",
                    dashboard_title="Configured Dashboard",
                    snapshot_description_template="Configured {snapshot_date} description",
                ),
            )
        )

        fake_streamlit = self.load_app(fake_config=fake_config)

        self.assertEqual(fake_streamlit.page_config_calls[0]["page_title"], "Configured Title")
        self.assertTrue(any("Configured Dashboard" in body for body in fake_streamlit.markdown_calls))
        self.assertTrue(any("Configured 20260408 description" in body for body in fake_streamlit.markdown_calls))

    def test_overview_top_exposures_shows_four_charts_without_duplicate_tables(self) -> None:
        fake_streamlit = self.load_app()

        overview_exposure_tables = [
            call
            for call in fake_streamlit.dataframe_calls
            if list(getattr(call["data"], "columns", [])) in (
                ["company", "contribution_pct"],
                ["country", "contribution_pct"],
                ["sector", "contribution_pct"],
            )
            and call["kwargs"].get("height") == 320
        ]

        self.assertEqual(overview_exposure_tables, [])
        self.assertTrue(
            {"Top companies", "Top countries", "Top sectors", "Top continents"}.issubset(
                set(title for title in fake_streamlit.bar_titles if title)
            )
        )

    def test_single_etf_analysis_shows_counts_continents_and_all_company_rows(self) -> None:
        fake_streamlit = self.load_app()

        self.assertIn(("Companies", "25"), fake_streamlit.metric_calls)
        self.assertIn(("Countries", "3"), fake_streamlit.metric_calls)
        self.assertIn(("Sectors", "2"), fake_streamlit.metric_calls)
        self.assertIn("SWDA Top continents", set(title for title in fake_streamlit.bar_titles if title))

        company_weight_tables = [
            call
            for call in fake_streamlit.dataframe_calls
            if list(getattr(call["data"], "columns", [])) == ["company", "weight_pct"]
            and call["kwargs"].get("height") == 360
        ]

        self.assertEqual(len(company_weight_tables), 1)
        self.assertEqual(len(company_weight_tables[0]["data"]), 25)

    def test_breakdown_tables_use_etf_weight_and_show_holdings_count(self) -> None:
        fake_streamlit = self.load_app()

        company_breakdown_tables = [
            call
            for call in fake_streamlit.dataframe_calls
            if call["kwargs"].get("height") == 340
            and list(getattr(call["data"], "columns", []))
            == ["company", "parent_etf", "contribution_pct", "underlying_weight_pct", "line_items"]
        ]
        self.assertEqual(len(company_breakdown_tables), 1)
        company_config = company_breakdown_tables[0]["kwargs"]["column_config"]
        self.assertEqual(company_config["underlying_weight_pct"]["args"][0], "ETF weight")
        self.assertEqual(company_config["line_items"]["args"][0], "Holdings count")

        etf_breakdown_tables = [
            call
            for call in fake_streamlit.dataframe_calls
            if call["kwargs"].get("height") == 280
            and "underlying_weight_pct" in getattr(call["data"], "columns", [])
            and "line_items" in getattr(call["data"], "columns", [])
        ]
        self.assertGreaterEqual(len(etf_breakdown_tables), 3)
        for call in etf_breakdown_tables:
            column_config = call["kwargs"]["column_config"]
            self.assertEqual(column_config["underlying_weight_pct"]["args"][0], "ETF weight")
            self.assertEqual(column_config["line_items"]["args"][0], "Holdings count")

        cash_equivalent_tables = [
            call
            for call in fake_streamlit.dataframe_calls
            if list(getattr(call["data"], "columns", []))
            == [
                "company",
                "parent_etf",
                "country",
                "sector",
                "asset_class",
                "holding_type",
                "weight_pct",
                "contribution_pct",
            ]
        ]
        self.assertEqual(len(cash_equivalent_tables), 1)
        cash_config = cash_equivalent_tables[0]["kwargs"]["column_config"]
        self.assertEqual(cash_config["weight_pct"]["args"][0], "ETF weight")
        self.assertEqual(cash_config["contribution_pct"]["args"][0], "Portfolio weight")
        self.assertIn(("Portfolio weight", "0.40%"), fake_streamlit.metric_calls)

        contribution_tables = [
            call
            for call in fake_streamlit.dataframe_calls
            if "contribution_pct" in getattr(call["data"], "columns", [])
            and "column_config" in call["kwargs"]
            and "contribution_pct" in call["kwargs"]["column_config"]
        ]
        self.assertTrue(contribution_tables)
        for call in contribution_tables:
            contribution_config = call["kwargs"]["column_config"]["contribution_pct"]
            self.assertEqual(contribution_config["args"][0], "Portfolio weight")

        self.assertTrue(fake_streamlit.bar_figures)
        self.assertTrue(
            all(
                figure.updated_layout.get("xaxis_title") == "Portfolio weight (%)"
                for figure in fake_streamlit.bar_figures
                if "xaxis_title" in figure.updated_layout
            )
        )
