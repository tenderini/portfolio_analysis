import tempfile
import unittest
from pathlib import Path

from src.portfolio_analysis_app.generate_etf_catalog import (
    build_supported_catalog,
    normalise_catalog_candidate,
    write_catalog,
)


class GenerateEtfCatalogTests(unittest.TestCase):
    def test_normalise_catalog_candidate_builds_stable_etf_id_and_search_text(self) -> None:
        candidate = normalise_catalog_candidate(
            {
                "symbol": "swda",
                "isin": "ie00b4l5y983",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/swda",
                "holdings_url": "https://example.test/swda.csv",
            }
        )

        self.assertEqual(candidate["etf_id"], "ishares-swda-ie00b4l5y983")
        self.assertIn("swda", candidate["search_text"])
        self.assertIn("ie00b4l5y983", candidate["search_text"])

    def test_build_supported_catalog_rejects_missing_isin_and_duplicate_isin(self) -> None:
        candidates = [
            {
                "symbol": "SWDA",
                "isin": "IE00B4L5Y983",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/swda",
                "holdings_url": "https://example.test/swda.csv",
            },
            {
                "symbol": "SWD2",
                "isin": "IE00B4L5Y983",
                "display_name": "Duplicate World ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/swd2",
                "holdings_url": "https://example.test/swd2.csv",
            },
            {
                "symbol": "BROKEN",
                "isin": "",
                "display_name": "Broken ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/broken",
                "holdings_url": "https://example.test/broken.csv",
            },
        ]

        catalog, report = build_supported_catalog(candidates, validator=lambda candidate: (True, ""))

        self.assertEqual([entry["symbol"] for entry in catalog], ["SWDA"])
        self.assertEqual(report["rejected"]["missing_isin"], 1)
        self.assertEqual(report["rejected"]["duplicate_isin"], 1)

    def test_write_catalog_sorts_entries_deterministically(self) -> None:
        catalog = [
            {
                "etf_id": "ishares-zeta-ie00zzzzzz01",
                "issuer_key": "ishares",
                "symbol": "ZETA",
                "isin": "IE00ZZZZZZ01",
                "display_name": "Zeta ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/zeta",
                "holdings_url": "https://example.test/zeta.csv",
                "search_text": "zeta ie00zzzzzz01 zeta etf",
            },
            {
                "etf_id": "ishares-alpha-ie00aaaaaa01",
                "issuer_key": "ishares",
                "symbol": "ALPHA",
                "isin": "IE00AAAAAA01",
                "display_name": "Alpha ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/alpha",
                "holdings_url": "https://example.test/alpha.csv",
                "search_text": "alpha ie00aaaaaa01 alpha etf",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "etf_catalog.json"
            write_catalog(catalog, output_path)
            saved = output_path.read_text(encoding="utf-8")

        self.assertLess(saved.find('"display_name": "Alpha ETF"'), saved.find('"display_name": "Zeta ETF"'))
