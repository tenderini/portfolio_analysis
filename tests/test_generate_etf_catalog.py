import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.portfolio_analysis_app.generate_etf_catalog as generate_etf_catalog
from src.portfolio_analysis_app.generate_etf_catalog import (
    build_catalog_report,
    build_supported_catalog,
    discover_ishares_candidates,
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

    def test_normalise_catalog_candidate_adds_site_entry_passthrough_to_ishares_product_urls(self) -> None:
        candidate = normalise_catalog_candidate(
            {
                "symbol": "swda",
                "isin": "ie00b4l5y983",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Equity",
                "product_url": "https://www.ishares.com/uk/individual/en/products/251882/ishares-msci-world-ucits-etf-acc-fund",
                "holdings_url": "https://example.test/swda.csv",
            }
        )

        self.assertEqual(
            candidate["product_url"],
            "https://www.ishares.com/uk/individual/en/products/251882/ishares-msci-world-ucits-etf-acc-fund?siteEntryPassthrough=true",
        )

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
        self.assertEqual(report["reason_counts"]["parse_failed"], 1)

    def test_build_supported_catalog_logs_validation_progress(self) -> None:
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
                "symbol": "EIMI",
                "isin": "IE00BKM4GZ66",
                "display_name": "iShares Core MSCI EM IMI UCITS ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/eimi",
                "holdings_url": "",
            },
        ]

        with self.assertLogs(generate_etf_catalog.__name__, level="INFO") as captured:
            build_supported_catalog(candidates, validator=lambda candidate: (True, "", ""))

        log_output = "\n".join(captured.output)
        self.assertIn("Validating support for 2 ETF candidates", log_output)
        self.assertIn("Validated candidate 1/2 (SWDA)", log_output)
        self.assertIn("Validated candidate 2/2 (EIMI)", log_output)

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
                "https://www.ishares.com/uk/individual/en/products/264659/ishares-msci-emerging-markets-imi-ucits-etf?siteEntryPassthrough=true",
                "https://www.ishares.com/uk/individual/en/products/251882/ishares-msci-world-ucits-etf-acc-fund?siteEntryPassthrough=true",
            ],
        )

    def test_discover_ishares_candidates_logs_page_progress(self) -> None:
        first_page_candidates = [
            {
                "symbol": "SWDA",
                "isin": "",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Unknown",
                "product_url": "https://example.test/swda",
                "holdings_url": "",
            }
        ]

        with (
            patch.object(
                generate_etf_catalog,
                "_fetch_discovery_html",
                side_effect=["page-1-html", "page-2-html"],
            ),
            patch.object(
                generate_etf_catalog,
                "_extract_candidates_from_discovery_html",
                side_effect=[first_page_candidates, []],
            ),
            patch.object(
                generate_etf_catalog,
                "_enrich_candidate_identity",
                side_effect=lambda candidate: {**candidate, "isin": "IE00B4L5Y983"},
            ),
            self.assertLogs(generate_etf_catalog.__name__, level="INFO") as captured,
        ):
            candidates, used_fallback = discover_ishares_candidates()

        self.assertFalse(used_fallback)
        self.assertEqual(len(candidates), 1)
        log_output = "\n".join(captured.output)
        self.assertIn("Discovering iShares ETF candidates", log_output)
        self.assertIn("Fetched discovery page 1/4", log_output)
        self.assertIn("Page 1 yielded 1 raw candidates", log_output)
        self.assertIn("Fetched discovery page 2/4", log_output)
        self.assertIn("Page 2 yielded 0 raw candidates", log_output)
        self.assertIn("Enriching 1 unique ETF candidates", log_output)

    def test_discover_ishares_candidates_stops_at_hardcoded_limit(self) -> None:
        many_candidates = [
            {
                "symbol": f"ETF{i}",
                "isin": "",
                "display_name": f"ETF {i}",
                "asset_class": "Unknown",
                "product_url": f"https://example.test/etf-{i}",
                "holdings_url": "",
            }
            for i in range(60)
        ]

        with (
            patch.object(generate_etf_catalog, "_fetch_discovery_html", return_value="page-1-html"),
            patch.object(
                generate_etf_catalog,
                "_extract_candidates_from_discovery_html",
                return_value=many_candidates,
            ),
            patch.object(
                generate_etf_catalog,
                "_enrich_candidate_identity",
                side_effect=lambda candidate: {**candidate, "isin": f"IE00TEST{candidate['symbol'][-4:]}"},
            ),
            patch.object(
                generate_etf_catalog,
                "get_discovery_candidate_limit",
                return_value=generate_etf_catalog.DISCOVERY_CANDIDATE_LIMIT,
            ),
            self.assertLogs(generate_etf_catalog.__name__, level="INFO") as captured,
        ):
            candidates, used_fallback = discover_ishares_candidates()

        self.assertFalse(used_fallback)
        self.assertEqual(len(candidates), generate_etf_catalog.DISCOVERY_CANDIDATE_LIMIT)
        log_output = "\n".join(captured.output)
        self.assertIn(
            f"Applying configured discovery limit: {generate_etf_catalog.DISCOVERY_CANDIDATE_LIMIT} ETF candidates",
            log_output,
        )
        self.assertIn(
            f"Reached configured discovery limit of {generate_etf_catalog.DISCOVERY_CANDIDATE_LIMIT} ETF candidates",
            log_output,
        )

    def test_discover_ishares_candidates_uses_unlimited_mode_when_limit_is_none(self) -> None:
        many_candidates = [
            {
                "symbol": f"ETF{i}",
                "isin": "",
                "display_name": f"ETF {i}",
                "asset_class": "Unknown",
                "product_url": f"https://example.test/etf-{i}",
                "holdings_url": "",
            }
            for i in range(12)
        ]

        with (
            patch.object(generate_etf_catalog, "_fetch_discovery_html", return_value="page-1-html"),
            patch.object(
                generate_etf_catalog,
                "_extract_candidates_from_discovery_html",
                return_value=many_candidates,
            ),
            patch.object(
                generate_etf_catalog,
                "_enrich_candidate_identity",
                side_effect=lambda candidate: {**candidate, "isin": f"IE00TEST{candidate['symbol'][-4:]}"},
            ),
            patch.object(generate_etf_catalog, "get_discovery_candidate_limit", return_value=None),
            self.assertLogs(generate_etf_catalog.__name__, level="INFO") as captured,
        ):
            candidates, used_fallback = discover_ishares_candidates()

        self.assertFalse(used_fallback)
        self.assertEqual(len(candidates), 12)
        log_output = "\n".join(captured.output)
        self.assertIn("Applying unlimited discovery candidate limit", log_output)
        self.assertNotIn("Reached configured discovery limit", log_output)

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
