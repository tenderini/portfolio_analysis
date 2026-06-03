import unittest
from unittest.mock import Mock, patch

import pandas as pd

import src.portfolio_analysis_app.data_retrival as data_retrival
from src.portfolio_analysis_app.data_retrival import extract_holdings_csv_url


class DataRetrivalTests(unittest.TestCase):
    def test_extract_holdings_csv_url_joins_relative_ajax_links_without_query_leakage(self) -> None:
        product_page_url = (
            "https://www.ishares.com/uk/individual/en/products/251882/"
            "ishares-msci-world-ucits-etf-acc-fund?siteEntryPassthrough=true"
        )
        rendered_html = """
        <html>
          <body>
            <a href="/uk/individual/en/products/251882/ishares-msci-world-ucits-etf-acc-fund/1506575576011.ajax?fileType=csv&amp;fileName=SWDA_holdings&amp;dataType=fund">
              Download holdings
            </a>
          </body>
        </html>
        """

        csv_url = extract_holdings_csv_url(product_page_url, rendered_html)

        self.assertEqual(
            csv_url,
            "https://www.ishares.com/uk/individual/en/products/251882/"
            "ishares-msci-world-ucits-etf-acc-fund/1506575576011.ajax"
            "?fileType=csv&fileName=SWDA_holdings&dataType=fund",
        )

    def test_fetch_standardised_holdings_routes_vanguard_entries_to_vanguard_provider(self) -> None:
        expected_holdings = pd.DataFrame(
            {
                "company": ["Apple Inc."],
                "country": ["North America"],
                "sector": ["Technology"],
                "asset_class": ["Equity"],
                "weight_pct": [4.5],
                "holding_type": ["security"],
                "is_cash_equivalent": [False],
            }
        )
        expected_validation = Mock()

        with patch.object(
            data_retrival,
            "fetch_standardised_vanguard_holdings_snapshot",
            return_value=(expected_holdings, expected_validation, "https://example.test/vwrp.csv"),
        ) as fetch_mock:
            holdings, validation, holdings_url = data_retrival.fetch_standardised_holdings_snapshot(
                symbol="VWRP",
                isin="IE00BK5BQT80",
                product_page="https://example.test/vwrp",
                issuer_key="vanguard",
                holdings_url="https://example.test/vwrp.csv",
            )

        self.assertIs(holdings, expected_holdings)
        self.assertIs(validation, expected_validation)
        self.assertEqual(holdings_url, "https://example.test/vwrp.csv")
        fetch_mock.assert_called_once_with(
            symbol="VWRP",
            isin="IE00BK5BQT80",
            product_page="https://example.test/vwrp",
            holdings_url="https://example.test/vwrp.csv",
        )

    def test_fetch_standardised_holdings_rejects_unknown_issuer(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported ETF issuer: mystery"):
            data_retrival.fetch_standardised_holdings_snapshot(
                symbol="TEST",
                isin="IE00TEST0001",
                product_page="https://example.test/test",
                issuer_key="mystery",
            )

    def test_standardise_vanguard_equity_holdings_maps_name_weight_sector_and_region(self) -> None:
        raw_df = pd.DataFrame(
            {
                "Holding name": ["Apple Inc.", "Microsoft Corp."],
                "% of market value": ["4.50%", "3.80%"],
                "Sector": ["Technology", "Technology"],
                "Region": ["North America", "North America"],
            }
        )

        holdings = data_retrival.standardise_vanguard_holdings(
            raw_df,
            symbol="VWRP",
            asset_class="Equity",
        )

        self.assertEqual(holdings["company"].tolist(), ["Apple Inc.", "Microsoft Corp."])
        self.assertEqual(holdings["country"].tolist(), ["North America", "North America"])
        self.assertEqual(holdings["sector"].tolist(), ["Technology", "Technology"])
        self.assertEqual(holdings["asset_class"].tolist(), ["Equity", "Equity"])
        self.assertEqual(holdings["weight_pct"].tolist(), [4.5, 3.8])
        self.assertEqual(holdings["holding_type"].tolist(), ["security", "security"])

    def test_standardise_vanguard_fixed_income_holdings_keeps_bonds_without_inferred_country(self) -> None:
        raw_df = pd.DataFrame(
            {
                "Holding name": ["US TREASURY N/B 4.125 11/15/2032", "JAPAN GOVT 0.1 03/20/2030"],
                "% of market value": [1.25, 0.75],
                "Market value": [1250000, 750000],
            }
        )

        holdings = data_retrival.standardise_vanguard_holdings(
            raw_df,
            symbol="VAGS",
            asset_class="Fixed Income",
        )

        self.assertEqual(
            holdings["company"].tolist(),
            ["US TREASURY N/B 4.125 11/15/2032", "JAPAN GOVT 0.1 03/20/2030"],
        )
        self.assertEqual(holdings["country"].tolist(), ["Unknown", "Unknown"])
        self.assertEqual(holdings["sector"].tolist(), ["Fixed Income", "Fixed Income"])
        self.assertEqual(holdings["asset_class"].tolist(), ["Fixed Income", "Fixed Income"])
        self.assertEqual(holdings["weight_pct"].tolist(), [1.25, 0.75])
