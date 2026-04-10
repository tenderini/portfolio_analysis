import importlib.util
import json
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

    def test_load_catalog_checkpoint_returns_empty_rows_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "etf_catalog.checkpoint.json"

            rows = generate_etf_catalog._load_catalog_checkpoint(checkpoint_path)

        self.assertEqual(rows, [])

    def test_write_catalog_checkpoint_persists_rows_deterministically(self) -> None:
        rows = [
            {
                "etf_id": "ishares-alpha-ie00aaaaaa01",
                "issuer_key": "ishares",
                "symbol": "ALPHA",
                "isin": "IE00AAAAAA01",
                "display_name": "Alpha ETF",
                "asset_class": "Equity",
                "product_url": "https://example.test/alpha",
                "holdings_url": "",
                "search_text": "alpha ie00aaaaaa01 alpha etf",
                "support_status": "unsupported",
                "support_reason_code": "fetch_failed",
                "support_error_detail": "timeout",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "etf_catalog.checkpoint.json"

            generate_etf_catalog._write_catalog_checkpoint(
                completed_rows=rows,
                discovered_count=856,
                checkpoint_path=checkpoint_path,
            )

            saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))

        self.assertEqual(saved["version"], 1)
        self.assertEqual(saved["discovered_count"], 856)
        self.assertEqual(saved["completed_rows"], rows)

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
            self.assertLogs(generate_etf_catalog.__name__, level="INFO") as captured,
        ):
            candidates, used_fallback = discover_ishares_candidates()

        self.assertFalse(used_fallback)
        self.assertEqual(len(candidates), 1)
        log_output = "\n".join(captured.output)
        self.assertIn("Discovering iShares ETF candidates", log_output)
        self.assertIn("Fetched discovery page 1/", log_output)
        self.assertIn("Page 1 yielded 1 raw candidates", log_output)
        self.assertIn("Fetched discovery page 2/", log_output)
        self.assertIn("Page 2 yielded 0 raw candidates", log_output)
        self.assertIn("Discovered 1 ETF candidates", log_output)

    def test_discover_ishares_candidates_stops_at_configured_limit(self) -> None:
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
                "get_discovery_candidate_limit",
                return_value=10,
            ),
            self.assertLogs(generate_etf_catalog.__name__, level="INFO") as captured,
        ):
            candidates, used_fallback = discover_ishares_candidates()

        self.assertFalse(used_fallback)
        self.assertEqual(len(candidates), 10)
        log_output = "\n".join(captured.output)
        self.assertIn(
            "Applying configured discovery limit: 10 ETF candidates",
            log_output,
        )
        self.assertIn(
            "Reached configured discovery limit of 10 ETF candidates",
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
            patch.object(generate_etf_catalog, "get_discovery_candidate_limit", return_value=None),
            self.assertLogs(generate_etf_catalog.__name__, level="INFO") as captured,
        ):
            candidates, used_fallback = discover_ishares_candidates()

        self.assertFalse(used_fallback)
        self.assertEqual(len(candidates), 12)
        log_output = "\n".join(captured.output)
        self.assertIn("Applying unlimited discovery candidate limit", log_output)
        self.assertNotIn("Reached configured discovery limit", log_output)

    def test_discover_ishares_candidates_logs_processing_queue(self) -> None:
        raw_candidates = [
            {
                "symbol": "SWDA",
                "isin": "",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Unknown",
                "product_url": "https://example.test/swda",
                "holdings_url": "",
            },
            {
                "symbol": "EMIM",
                "isin": "",
                "display_name": "iShares Core MSCI Emerging Markets IMI UCITS ETF",
                "asset_class": "Unknown",
                "product_url": "https://example.test/emim",
                "holdings_url": "",
            },
        ]

        with (
            patch.object(generate_etf_catalog, "_fetch_discovery_html", return_value="page-1-html"),
            patch.object(generate_etf_catalog, "_extract_candidates_from_discovery_html", return_value=raw_candidates),
            patch.object(generate_etf_catalog, "get_discovery_candidate_limit", return_value=None),
            self.assertLogs(generate_etf_catalog.__name__, level="INFO") as captured,
        ):
            discover_ishares_candidates()

        log_output = "\n".join(captured.output)
        self.assertIn("Queued 2 ETF candidates for processing", log_output)
        self.assertIn("Queue: 1/2 SWDA - iShares Core MSCI World UCITS ETF", log_output)
        self.assertIn("Queue: 2/2 EMIM - iShares Core MSCI Emerging Markets IMI UCITS ETF", log_output)

    def test_process_catalog_candidates_skips_rows_already_in_checkpoint(self) -> None:
        checkpoint_rows = [
            normalise_catalog_candidate(
                {
                    "symbol": "SWDA",
                    "isin": "IE00B4L5Y983",
                    "display_name": "iShares Core MSCI World UCITS ETF",
                    "asset_class": "Equity",
                    "product_url": "https://example.test/swda",
                    "holdings_url": "",
                    "support_status": "unsupported",
                    "support_reason_code": "fetch_failed",
                    "support_error_detail": "timeout",
                }
            )
        ]
        raw_candidates = [
            {
                "symbol": "SWDA",
                "isin": "",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Unknown",
                "product_url": "https://example.test/swda",
                "holdings_url": "",
            },
            {
                "symbol": "EIMI",
                "isin": "",
                "display_name": "iShares Core MSCI EM IMI UCITS ETF",
                "asset_class": "Unknown",
                "product_url": "https://example.test/eimi",
                "holdings_url": "",
            },
        ]

        with (
            patch.object(generate_etf_catalog, "_load_catalog_checkpoint", return_value=checkpoint_rows),
            patch.object(
                generate_etf_catalog,
                "_process_catalog_candidate",
                return_value=normalise_catalog_candidate(
                    {
                        "symbol": "EIMI",
                        "isin": "IE00BKM4GZ66",
                        "display_name": "iShares Core MSCI EM IMI UCITS ETF",
                        "asset_class": "Equity",
                        "product_url": "https://example.test/eimi",
                        "holdings_url": "",
                        "support_status": "unsupported",
                        "support_reason_code": "fetch_failed",
                        "support_error_detail": "timeout",
                    }
                ),
            ) as process_mock,
        ):
            candidates = generate_etf_catalog._process_catalog_candidates(raw_candidates)

        self.assertEqual([entry["symbol"] for entry in candidates], ["EIMI", "SWDA"])
        self.assertEqual(process_mock.call_count, 1)
        self.assertEqual(process_mock.call_args[0][0]["symbol"], "EIMI")

    def test_process_catalog_candidates_logs_resume_progress_and_checkpoint_saves(self) -> None:
        checkpoint_rows = [
            normalise_catalog_candidate(
                {
                    "symbol": "SWDA",
                    "isin": "IE00B4L5Y983",
                    "display_name": "iShares Core MSCI World UCITS ETF",
                    "asset_class": "Equity",
                    "product_url": "https://example.test/swda",
                    "holdings_url": "",
                    "support_status": "unsupported",
                    "support_reason_code": "fetch_failed",
                    "support_error_detail": "timeout",
                }
            )
        ]
        raw_candidates = [
            {
                "symbol": "SWDA",
                "isin": "",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Unknown",
                "product_url": "https://example.test/swda",
                "holdings_url": "",
            },
            {
                "symbol": "IBGT",
                "isin": "",
                "display_name": "iShares $ Treasury Bond 1-3yr UCITS ETF",
                "asset_class": "Unknown",
                "product_url": "https://example.test/ibgt",
                "holdings_url": "",
            },
        ]
        processed_row = normalise_catalog_candidate(
            {
                "symbol": "IBGT",
                "isin": "IE00B1FZS798",
                "display_name": "iShares $ Treasury Bond 1-3yr UCITS ETF",
                "asset_class": "Fixed Income",
                "product_url": "https://example.test/ibgt",
                "holdings_url": "",
                "support_status": "unsupported",
                "support_reason_code": "fetch_failed",
                "support_error_detail": "timeout",
            }
        )

        with (
            patch.object(generate_etf_catalog, "_load_catalog_checkpoint", return_value=checkpoint_rows),
            patch.object(generate_etf_catalog, "_process_catalog_candidate", return_value=processed_row),
            patch.object(generate_etf_catalog, "_write_catalog_checkpoint"),
            self.assertLogs(generate_etf_catalog.__name__, level="INFO") as captured,
        ):
            generate_etf_catalog._process_catalog_candidates(raw_candidates)

        log_output = "\n".join(captured.output)
        self.assertIn("Loaded checkpoint with 1 completed ETFs; 1 remaining", log_output)
        self.assertIn(
            "Processing overall 2/2, remaining 1/1 (IBGT): iShares $ Treasury Bond 1-3yr UCITS ETF",
            log_output,
        )
        self.assertIn(
            "Completed overall 2/2, remaining 1/1 (IBGT): unsupported (fetch_failed)",
            log_output,
        )
        self.assertIn("Checkpoint saved with 2 completed ETFs", log_output)

    def test_process_catalog_candidate_returns_unsupported_row_when_enrichment_retries_fail(self) -> None:
        candidate = {
            "symbol": "FAIL",
            "isin": "",
            "display_name": "Fail ETF",
            "asset_class": "Unknown",
            "product_url": "https://example.test/fail",
            "holdings_url": "",
        }

        with patch.object(
            generate_etf_catalog,
            "_enrich_candidate_identity",
            side_effect=TimeoutError("timeout while loading product page"),
        ):
            row = generate_etf_catalog._process_catalog_candidate(candidate)

        self.assertEqual(row["symbol"], "FAIL")
        self.assertEqual(row["support_status"], "unsupported")
        self.assertEqual(row["support_reason_code"], "fetch_failed")
        self.assertIn("timeout", row["support_error_detail"])

    def test_process_catalog_candidate_marks_supported_row_after_successful_validation(self) -> None:
        candidate = {
            "symbol": "SWDA",
            "isin": "",
            "display_name": "iShares Core MSCI World UCITS ETF",
            "asset_class": "Unknown",
            "product_url": "https://example.test/swda",
            "holdings_url": "",
        }
        enriched = {
            **candidate,
            "isin": "IE00B4L5Y983",
            "asset_class": "Equity",
        }

        with (
            patch.object(generate_etf_catalog, "_enrich_candidate_identity", return_value=enriched),
            patch.object(
                generate_etf_catalog,
                "_validate_candidate_support",
                side_effect=lambda row: (row.update({"holdings_url": "https://example.test/swda.csv"}) or (True, "", "")),
            ),
        ):
            row = generate_etf_catalog._process_catalog_candidate(candidate)

        self.assertEqual(row["support_status"], "supported")
        self.assertEqual(row["holdings_url"], "https://example.test/swda.csv")

    def test_main_removes_checkpoint_after_successful_completion(self) -> None:
        discovered_candidates = [
            {
                "symbol": "SWDA",
                "isin": "",
                "display_name": "iShares Core MSCI World UCITS ETF",
                "asset_class": "Unknown",
                "product_url": "https://example.test/swda",
                "holdings_url": "",
            }
        ]
        processed_rows = [
            normalise_catalog_candidate(
                {
                    "symbol": "SWDA",
                    "isin": "IE00B4L5Y983",
                    "display_name": "iShares Core MSCI World UCITS ETF",
                    "asset_class": "Equity",
                    "product_url": "https://example.test/swda",
                    "holdings_url": "https://example.test/swda.csv",
                    "support_status": "supported",
                    "support_reason_code": "",
                    "support_error_detail": "",
                }
            )
        ]

        with (
            patch.object(generate_etf_catalog, "discover_ishares_candidates", return_value=(discovered_candidates, False)),
            patch.object(generate_etf_catalog, "_process_catalog_candidates", return_value=processed_rows),
            patch.object(generate_etf_catalog, "build_catalog_report", return_value={"supported": 1, "unsupported": 0}),
            patch.object(generate_etf_catalog, "write_catalog"),
            patch.object(generate_etf_catalog, "_clear_catalog_checkpoint") as clear_mock,
        ):
            generate_etf_catalog.main()

        clear_mock.assert_called_once()

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
