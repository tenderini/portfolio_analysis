import unittest

from src.portfolio_analysis_app.dashboard_metrics import build_summary_metrics


class BuildSummaryMetricsTests(unittest.TestCase):
    def test_build_summary_metrics_returns_only_selected_headline_cards(self) -> None:
        summary = {
            "total_holdings_count": 6483,
            "unique_companies": 6434,
            "unique_countries": 48,
            "unique_sectors": 12,
            "portfolio_total_pct": 99.92,
            "cash_equivalent_rows": 42,
        }

        metrics = build_summary_metrics(summary)

        self.assertEqual(
            metrics,
            [
                {"label": "Companies", "value": "6,434"},
                {"label": "Countries", "value": "48"},
                {"label": "Sectors", "value": "12"},
                {"label": "Portfolio total", "value": "99.92%"},
            ],
        )
