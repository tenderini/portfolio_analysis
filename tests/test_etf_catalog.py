import json
import tempfile
import unittest
from pathlib import Path

from src.portfolio_analysis_app.etf_catalog import (
    find_exact_catalog_match,
    load_etf_catalog,
    search_etf_catalog,
)


class EtfCatalogTests(unittest.TestCase):
    def test_load_etf_catalog_rejects_missing_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "etf_catalog.json"
            catalog_path.write_text(
                json.dumps(
                    [
                        {
                            "etf_id": "ishares-swda-ie00b4l5y983",
                            "issuer_key": "ishares",
                            "symbol": "SWDA",
                            "isin": "IE00B4L5Y983",
                            "display_name": "iShares Core MSCI World UCITS ETF",
                            "asset_class": "Equity",
                            "product_url": "https://example.test/swda",
                            "holdings_url": "https://example.test/swda.csv",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_etf_catalog(catalog_path)

    def test_find_exact_catalog_match_supports_ticker_and_isin(self) -> None:
        catalog = [
            {
                "etf_id": "ishares-swda-ie00b4l5y983",
                "issuer_key": "ishares",
                "symbol": "SWDA",
                "isin": "IE00B4L5Y983",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/swda",
                "holdings_url": "https://example.test/swda.csv",
                "search_text": "swda ie00b4l5y983 ishares core msci world ucits etf",
            }
        ]

        by_ticker = find_exact_catalog_match("swda", catalog)
        by_isin = find_exact_catalog_match("IE00B4L5Y983", catalog)

        self.assertEqual(by_ticker["etf_id"], "ishares-swda-ie00b4l5y983")
        self.assertEqual(by_isin["etf_id"], "ishares-swda-ie00b4l5y983")

    def test_search_etf_catalog_matches_partial_names(self) -> None:
        catalog = [
            {
                "etf_id": "ishares-swda-ie00b4l5y983",
                "issuer_key": "ishares",
                "symbol": "SWDA",
                "isin": "IE00B4L5Y983",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/swda",
                "holdings_url": "https://example.test/swda.csv",
                "search_text": "swda ie00b4l5y983 ishares core msci world ucits etf",
            },
            {
                "etf_id": "ishares-emim-ie00bkm4gz66",
                "issuer_key": "ishares",
                "symbol": "EMIM",
                "isin": "IE00BKM4GZ66",
                "display_name": "iShares Core MSCI Emerging Markets IMI UCITS ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/emim",
                "holdings_url": "https://example.test/emim.csv",
                "search_text": "emim ie00bkm4gz66 ishares core msci emerging markets imi ucits etf",
            },
        ]

        matches = search_etf_catalog("emerging markets", catalog)

        self.assertEqual([entry["symbol"] for entry in matches], ["EMIM"])
