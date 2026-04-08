import importlib.util
import sys
import types
import unittest
from pathlib import Path

import pandas as pd


class DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def metric(self, *args, **kwargs):
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
        return None

    def markdown(self, *args, **kwargs):
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

    def dataframe(self, *args, **kwargs):
        return None

    def bar_chart(self, *args, **kwargs):
        return None

    def plotly_chart(self, *args, **kwargs):
        return None

    def columns(self, count_or_widths):
        count = count_or_widths if isinstance(count_or_widths, int) else len(count_or_widths)
        return [DummyContext() for _ in range(count)]

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
    def update_traces(self, *args, **kwargs):
        return self

    def update_layout(self, *args, **kwargs):
        return self


def build_fake_report() -> dict:
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
            "cash_equivalent_rows": 0,
            "cash_equivalent_unique_labels": 0,
            "cash_equivalent_total_pct": 0.0,
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
            columns=[
                "company",
                "parent_etf",
                "country",
                "sector",
                "asset_class",
                "holding_type",
                "weight_pct",
                "contribution_pct",
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
                "company_exposure": pd.DataFrame({"company": ["Apple"], "weight_pct": [5.0]}),
                "country_exposure": pd.DataFrame({"country": ["US"], "weight_pct": [60.0]}),
                "sector_exposure": pd.DataFrame({"sector": ["Technology"], "weight_pct": [25.0]}),
            }
        },
    }


class AppLayoutTests(unittest.TestCase):
    def test_app_uses_fixed_defaults_without_sidebar_controls(self) -> None:
        fake_streamlit = FakeStreamlit()
        fake_theme = types.SimpleNamespace(
            BAR_COLOR_SCALE=[],
            DARK_ETF_COLOR_MAP={},
            TEXT_PRIMARY="#fff",
            apply_dark_figure_layout=lambda fig, title=None, height=None: fig,
            build_bar_value_axis_range=lambda values: [0.0, 1.0],
            build_theme_css=lambda: "<style></style>",
        )
        fake_metrics = types.SimpleNamespace(
            build_summary_metrics=lambda summary: [{"label": "Companies", "value": "2"}]
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
        fake_plotly = types.ModuleType("plotly")
        fake_plotly_express = types.SimpleNamespace(
            bar=lambda *args, **kwargs: FakeFigure(),
            pie=lambda *args, **kwargs: FakeFigure(),
        )
        previous_modules = {
            name: sys.modules.get(name)
            for name in [
                "streamlit",
                "app_theme",
                "dashboard_metrics",
                "portfolio_analysis",
                "plotly",
                "plotly.express",
            ]
        }
        sys.modules["streamlit"] = fake_streamlit
        sys.modules["app_theme"] = fake_theme
        sys.modules["dashboard_metrics"] = fake_metrics
        sys.modules["portfolio_analysis"] = fake_portfolio
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

        self.assertEqual(fake_streamlit.sidebar_enter_count, 0)
        self.assertNotIn("Top N", fake_streamlit.control_labels)
        self.assertNotIn("Search companies", fake_streamlit.control_labels)
        self.assertNotIn("Refresh analysis", fake_streamlit.control_labels)
        self.assertIn(
            ["Overview", "Companies", "Countries/Continents", "Sectors", "Overlap", "Single ETF Analysis"],
            fake_streamlit.tab_labels,
        )
        self.assertIn(["Countries", "Continents"], fake_streamlit.tab_labels)
