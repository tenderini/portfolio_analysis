import runpy
import sys
import types
import unittest
from pathlib import Path


class StopCalled(Exception):
    pass


class FakeStreamlit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.page_config_calls: list[dict] = []
        self.error_calls: list[tuple] = []
        self.control_labels: list[str] = []
        self.session_state: dict = {}

    def cache_data(self, **kwargs):
        def decorator(func):
            func.clear = lambda: None
            return func

        return decorator

    def set_page_config(self, **kwargs):
        self.page_config_calls.append(kwargs)
        return None

    def markdown(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        self.error_calls.append(args)
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def success(self, *args, **kwargs):
        return None

    def subheader(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def write(self, *args, **kwargs):
        return None

    def columns(self, count_or_widths):
        count = count_or_widths if isinstance(count_or_widths, int) else len(count_or_widths)
        return [self for _ in range(count)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def metric(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def plotly_chart(self, *args, **kwargs):
        return None

    def selectbox(self, label, options, index=0, format_func=None):
        self.control_labels.append(label)
        return list(options)[index]

    def text_input(self, label, value="", placeholder=None, **kwargs):
        self.control_labels.append(label)
        return value

    def number_input(self, label, value=0.0, **kwargs):
        self.control_labels.append(label)
        return value

    def button(self, label, **kwargs):
        self.control_labels.append(label)
        return False

    def tabs(self, labels):
        return [self for _ in labels]

    def expander(self, *args, **kwargs):
        return self

    def stop(self):
        raise StopCalled()


class PackageAppEntrypointTests(unittest.TestCase):
    def test_package_app_supports_direct_script_execution(self) -> None:
        fake_streamlit = FakeStreamlit()
        fake_pandas = types.ModuleType("pandas")
        fake_config = types.ModuleType("src.portfolio_analysis_app.app_config")
        fake_config.load_app_config = lambda: types.SimpleNamespace(
            ui=types.SimpleNamespace(show_portfolio_total_in_overview=False, top_n=20),
            content=types.SimpleNamespace(
                page_title="PIE Portfolio Analysis",
                dashboard_title="PIE Portfolio Look-Through Dashboard",
                snapshot_description_template="Snapshot {snapshot_date}",
            ),
        )
        fake_theme = types.ModuleType("src.portfolio_analysis_app.app_theme")
        fake_theme.BAR_COLOR_SCALE = []
        fake_theme.DARK_ETF_COLOR_MAP = {}
        fake_theme.TEXT_PRIMARY = "#fff"
        fake_theme.apply_dark_figure_layout = lambda fig, title=None, height=None: fig
        fake_theme.build_bar_value_axis_range = lambda values: [0.0, 1.0]
        fake_theme.build_theme_css = lambda: "<style></style>"
        fake_metrics = types.ModuleType("src.portfolio_analysis_app.dashboard_metrics")
        fake_metrics.build_summary_metrics = lambda summary: []
        fake_portfolio = types.ModuleType("src.portfolio_analysis_app.portfolio_analysis")
        fake_portfolio.build_report = lambda snapshot_date=None: {}
        fake_portfolio.build_report_from_holdings = lambda combined_holdings, snapshot_label, files=None, source_exposures=None, etf_descriptions=None: {}
        fake_portfolio.filter_company_exposure = lambda df, search_text="": df
        fake_portfolio.format_snapshot_date = lambda snapshot_date: snapshot_date
        fake_portfolio.get_company_drilldown = lambda df, company: df
        fake_portfolio.get_dimension_drilldown = (
            lambda etf_breakdown, company_drivers, dimension, value: {}
        )
        fake_portfolio.list_available_snapshot_dates = lambda: []
        fake_custom_portfolios = types.ModuleType("src.portfolio_analysis_app.custom_portfolios")
        fake_custom_portfolios.DEFAULT_PORTFOLIO_NAME = "PIE Default"
        fake_custom_portfolios.load_saved_portfolios = lambda data_dir=None: []
        fake_custom_portfolios.save_saved_portfolios = lambda portfolios, data_dir=None: None
        fake_custom_portfolios.resolve_portfolio_entries = lambda entries: []
        fake_custom_portfolios.validate_portfolio_entries = (
            lambda entries: {"is_valid": False, "errors": ["No saved portfolios are available."], "total_weight_pct": 0.0}
        )
        fake_custom_portfolios.build_combined_holdings_for_portfolio = (
            lambda entries, data_dir=None: {"combined_holdings": {}, "snapshot_label": "", "etf_descriptions": []}
        )
        fake_custom_portfolios.refresh_supported_etf_snapshot = lambda entry, data_dir=None: None
        fake_etf_catalog = types.ModuleType("src.portfolio_analysis_app.etf_catalog")
        fake_etf_catalog.load_etf_catalog = lambda catalog_path=None: []
        fake_etf_catalog.search_etf_catalog = lambda query, catalog=None, limit=20: []
        fake_etf_catalog.build_catalog_dataframe = lambda catalog=None, data_dir=None: {}
        fake_plotly = types.ModuleType("plotly")
        fake_plotly_express = types.ModuleType("plotly.express")

        previous_modules = {
            name: sys.modules.get(name)
            for name in [
                "pandas",
                "plotly",
                "plotly.express",
                "streamlit",
                "src",
                "src.portfolio_analysis_app",
                "src.portfolio_analysis_app.app_config",
                "src.portfolio_analysis_app.app_theme",
                "src.portfolio_analysis_app.dashboard_metrics",
                "src.portfolio_analysis_app.portfolio_analysis",
                "src.portfolio_analysis_app.custom_portfolios",
                "src.portfolio_analysis_app.etf_catalog",
            ]
        }
        sys.modules["pandas"] = fake_pandas
        sys.modules["plotly"] = fake_plotly
        sys.modules["plotly.express"] = fake_plotly_express
        sys.modules["streamlit"] = fake_streamlit
        sys.modules["src"] = types.ModuleType("src")
        sys.modules["src.portfolio_analysis_app"] = types.ModuleType("src.portfolio_analysis_app")
        sys.modules["src.portfolio_analysis_app.app_config"] = fake_config
        sys.modules["src.portfolio_analysis_app.app_theme"] = fake_theme
        sys.modules["src.portfolio_analysis_app.dashboard_metrics"] = fake_metrics
        sys.modules["src.portfolio_analysis_app.portfolio_analysis"] = fake_portfolio
        sys.modules["src.portfolio_analysis_app.custom_portfolios"] = fake_custom_portfolios
        sys.modules["src.portfolio_analysis_app.etf_catalog"] = fake_etf_catalog

        try:
            with self.assertRaises(StopCalled):
                runpy.run_path(Path("src/portfolio_analysis_app/app.py"), run_name="__main__")
        finally:
            for name, previous_module in previous_modules.items():
                if previous_module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous_module

        self.assertEqual(fake_streamlit.page_config_calls[0]["page_title"], "PIE Portfolio Analysis")
        self.assertEqual(fake_streamlit.error_calls, [("No saved portfolios are available.",)])
