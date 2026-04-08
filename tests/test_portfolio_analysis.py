import unittest

import pandas as pd

from portfolio_analysis import (
    _build_etf_composition,
    _build_single_etf_dimension_exposure,
    build_report,
)


class BuildEtfCompositionTests(unittest.TestCase):
    def test_build_etf_composition_collapses_duplicate_holdings_to_one_row_per_etf(self) -> None:
        combined_holdings = pd.DataFrame(
            {
                "parent_etf": ["SWDA", "SWDA", "EMIM", "WSML"],
                "pie_weight": [0.78, 0.78, 0.12, 0.10],
                "company": ["A", "B", "C", "D"],
                "contribution_pct": [1.0, 2.0, 3.0, 4.0],
            }
        )

        composition = _build_etf_composition(combined_holdings)

        self.assertEqual(composition["parent_etf"].tolist(), ["SWDA", "EMIM", "WSML"])
        self.assertEqual(composition["allocation_pct"].round(2).tolist(), [78.0, 12.0, 10.0])
        self.assertAlmostEqual(composition["allocation_pct"].sum(), 100.0, places=6)

    def test_build_report_exposes_etf_composition(self) -> None:
        report = build_report(snapshot_date="20260408")

        self.assertIn("etf_composition", report)
        self.assertEqual(report["etf_composition"]["parent_etf"].tolist(), ["SWDA", "EMIM", "WSML"])
        self.assertAlmostEqual(report["etf_composition"]["allocation_pct"].sum(), 100.0, places=6)

    def test_build_single_etf_dimension_exposure_uses_weight_pct_for_selected_etf(self) -> None:
        combined_holdings = pd.DataFrame(
            {
                "parent_etf": ["SWDA", "SWDA", "EMIM", "SWDA"],
                "company": ["Apple", "Microsoft", "Tencent", "Apple"],
                "country": ["US", "US", "CN", "US"],
                "sector": ["Tech", "Tech", "Tech", "Tech"],
                "weight_pct": [6.0, 4.0, 9.0, 1.5],
                "contribution_pct": [1.0, 2.0, 3.0, 4.0],
            }
        )

        exposure = _build_single_etf_dimension_exposure(combined_holdings, "SWDA", "company")

        self.assertEqual(exposure["company"].tolist(), ["Apple", "Microsoft"])
        self.assertEqual(exposure["weight_pct"].round(2).tolist(), [7.5, 4.0])
        self.assertAlmostEqual(exposure["weight_pct"].sum(), 11.5, places=6)

    def test_build_report_exposes_single_etf_analysis_inputs(self) -> None:
        report = build_report(snapshot_date="20260408")

        self.assertEqual(report["single_etf_options"], ["EMIM", "SWDA", "WSML"])
        swda = report["single_etf_analysis"]["SWDA"]
        self.assertIn("company_exposure", swda)
        self.assertIn("country_exposure", swda)
        self.assertIn("sector_exposure", swda)
        self.assertTrue((swda["company_exposure"]["weight_pct"] >= 0).all())
