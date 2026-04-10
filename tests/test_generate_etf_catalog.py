import importlib.util
import tempfile
import unittest
from pathlib import Path

from src.portfolio_analysis_app.generate_etf_catalog import (
    build_catalog_report,
    build_supported_catalog,
    _extract_candidates_from_discovery_html,
    normalise_catalog_candidate,
    write_catalog,
)


class GenerateEtfCatalogTests(unittest.TestCase):
    def test_generate_etf_catalog_supports_direct_script_import(self) -> None:
        module_path = Path("src/portfolio_analysis_app/generate_etf_catalog.py")
        spec = importlib.util.spec_from_file_location("generate_etf_catalog_script", module_path)

        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertTrue(callable(module.normalise_catalog_candidate))

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

        catalog, report = build_supported_catalog(candidates, validator=lambda candidate: (True, "", ""))

        self.assertEqual([entry["symbol"] for entry in catalog], ["SWDA"])
        self.assertEqual(report["reason_counts"]["missing_isin"], 1)
        self.assertEqual(report["reason_counts"]["duplicate_isin"], 1)

    def test_build_supported_catalog_keeps_unsupported_rows_with_reason_codes(self) -> None:
        candidates = [
            {
                "symbol": "SWDA",
                "isin": "IE00B4L5Y983",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/swda",
                "holdings_url": "",
            },
            {
                "symbol": "BAD",
                "isin": "IE00BADBAD01",
                "display_name": "Broken ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/bad",
                "holdings_url": "",
            },
        ]

        def validator(candidate):
            if candidate["symbol"] == "BAD":
                return False, "parse_failed", "Unable to parse holdings CSV."
            candidate["holdings_url"] = "https://example.test/swda.csv"
            return True, "", ""

        catalog, report = build_supported_catalog(candidates, validator=validator)

        self.assertEqual(len(catalog), 2)
        unsupported = next(entry for entry in catalog if entry["symbol"] == "BAD")
        self.assertEqual(unsupported["support_status"], "unsupported")
        self.assertEqual(unsupported["support_reason_code"], "parse_failed")
        self.assertEqual(report["supported"], 1)
        self.assertEqual(report["unsupported"], 1)

    def test_build_catalog_report_marks_fallback_usage(self) -> None:
        report = build_catalog_report(
            discovered=3,
            catalog=[
                {"symbol": "SWDA", "support_status": "supported", "support_reason_code": ""},
                {"symbol": "BAD", "support_status": "unsupported", "support_reason_code": "parse_failed"},
            ],
            used_fallback=True,
        )

        self.assertTrue(report["used_fallback"])
        self.assertEqual(report["reason_counts"]["parse_failed"], 1)

    def test_extract_candidates_from_discovery_html_parses_etf_table_rows(self) -> None:
        html = """
        <table>
          <tr>
            <td class="links"><a href="/uk/individual/en/products/251882/ishares-msci-world-ucits-etf-acc-fund">SWDA</a></td>
            <td class="links"><a href="/uk/individual/en/products/251882/ishares-msci-world-ucits-etf-acc-fund">iShares Core MSCI World UCITS ETF</a></td>
            <td class="column-left-line">USD</td>
          </tr>
          <tr>
            <td class="links"><a href="/uk/individual/en/products/264659/ishares-msci-emerging-markets-imi-ucits-etf">EIMI</a></td>
            <td class="links"><a href="/uk/individual/en/products/264659/ishares-msci-emerging-markets-imi-ucits-etf">iShares Core MSCI EM IMI UCITS ETF</a></td>
            <td class="column-left-line">USD</td>
          </tr>
        </table>
        """

        candidates = sorted(
            _extract_candidates_from_discovery_html(html),
            key=lambda entry: entry["symbol"],
        )

        self.assertEqual([entry["symbol"] for entry in candidates], ["EIMI", "SWDA"])
        self.assertEqual(
            [entry["product_url"] for entry in candidates],
            [
                "https://www.ishares.com/uk/individual/en/products/264659/ishares-msci-emerging-markets-imi-ucits-etf",
                "https://www.ishares.com/uk/individual/en/products/251882/ishares-msci-world-ucits-etf-acc-fund",
            ],
        )

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
                "support_status": "supported",
                "support_reason_code": "",
                "support_error_detail": "",
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
                "support_status": "supported",
                "support_reason_code": "",
                "support_error_detail": "",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "etf_catalog.json"
            write_catalog(catalog, output_path)
            saved = output_path.read_text(encoding="utf-8")

        self.assertLess(saved.find('"display_name": "Alpha ETF"'), saved.find('"display_name": "Zeta ETF"'))
