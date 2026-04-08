import unittest

from src.portfolio_analysis_app.app_theme import (
    DARK_ETF_COLOR_MAP,
    apply_dark_figure_layout,
    build_bar_value_axis_range,
    build_theme_css,
)


class FakeFigure:
    def __init__(self) -> None:
        self.updated_layout: dict = {}

    def update_layout(self, **kwargs):
        self.updated_layout.update(kwargs)
        return self


class DarkThemeTests(unittest.TestCase):
    def test_build_theme_css_includes_premium_dark_tokens(self) -> None:
        css = build_theme_css()

        self.assertIn("--bg-main:", css)
        self.assertIn("--accent:", css)
        self.assertIn(".dashboard-hero", css)
        self.assertIn(".content-panel", css)

    def test_build_theme_css_styles_sidebar_tabs_and_metric_cards(self) -> None:
        css = build_theme_css()

        self.assertIn('[data-testid="stSidebar"]', css)
        self.assertIn('[data-testid="stMetric"]', css)
        self.assertIn('[data-baseweb="tab-list"]', css)
        self.assertIn('[data-baseweb="tab-highlight"]', css)
        self.assertIn(".stPlotlyChart", css)
        self.assertIn(".dashboard-banner", css)
        self.assertIn("color-scheme: dark", css)
        self.assertIn('[data-testid="stToolbar"]', css)

    def test_build_theme_css_hides_sidebar_and_collapsed_toggle(self) -> None:
        css = build_theme_css()

        self.assertIn('[data-testid="stSidebar"] {', css)
        self.assertIn("display: none !important;", css)
        self.assertIn('[data-testid="stSidebarCollapsedControl"]', css)

    def test_apply_dark_figure_layout_sets_dark_background_and_font_colors(self) -> None:
        figure = FakeFigure()

        themed = apply_dark_figure_layout(figure, "Exposure", 420)

        self.assertIs(themed, figure)
        self.assertEqual(figure.updated_layout["paper_bgcolor"], "rgba(0, 0, 0, 0)")
        self.assertEqual(figure.updated_layout["plot_bgcolor"], "#111827")
        self.assertEqual(figure.updated_layout["font"]["color"], "#e5eef5")
        self.assertEqual(figure.updated_layout["height"], 420)

    def test_apply_dark_figure_layout_adds_dark_axis_grid_and_margins(self) -> None:
        figure = FakeFigure()

        themed = apply_dark_figure_layout(figure, "Top companies", 500)

        self.assertIs(themed, figure)
        self.assertEqual(figure.updated_layout["xaxis"]["gridcolor"], "rgba(138, 160, 181, 0.18)")
        self.assertEqual(figure.updated_layout["yaxis"]["gridcolor"], "rgba(138, 160, 181, 0.10)")
        self.assertEqual(figure.updated_layout["margin"]["t"], 56)

    def test_dark_etf_color_map_keeps_all_expected_symbols(self) -> None:
        self.assertEqual(set(DARK_ETF_COLOR_MAP), {"SWDA", "EMIM", "WSML"})

    def test_apply_dark_figure_layout_omits_title_when_not_provided(self) -> None:
        figure = FakeFigure()

        apply_dark_figure_layout(figure, None, 360)

        self.assertNotIn("title", figure.updated_layout)

    def test_build_bar_value_axis_range_adds_headroom_for_outside_labels(self) -> None:
        axis_range = build_bar_value_axis_range([24.9, 18.2, 11.4])

        self.assertEqual(axis_range[0], 0.0)
        self.assertGreater(axis_range[1], 24.9)
        self.assertGreaterEqual(axis_range[1], 29.0)

    def test_build_bar_value_axis_range_returns_default_when_values_are_empty(self) -> None:
        self.assertEqual(build_bar_value_axis_range([]), [0.0, 1.0])

    def test_build_theme_css_styles_etf_description_cards(self) -> None:
        css = build_theme_css()

        self.assertIn(".etf-description-card", css)
        self.assertIn(".etf-description-ticker", css)
        self.assertIn(".etf-description-role", css)
        self.assertIn(".etf-description-spacer", css)
