import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.portfolio_analysis_app.custom_portfolios import (
    DEFAULT_PORTFOLIO_NAME,
    build_combined_holdings_for_portfolio,
    load_saved_portfolios,
    refresh_supported_etf_snapshot,
    resolve_portfolio_entries,
    save_saved_portfolios,
    validate_portfolio_entries,
)


class SavedPortfolioTests(unittest.TestCase):
    @staticmethod
    def _catalog_entry(**overrides: object) -> dict[str, object]:
        entry: dict[str, object] = {
            "etf_id": "ishares-swda-ie00b4l5y983",
            "issuer_key": "ishares",
            "symbol": "SWDA",
            "isin": "IE00B4L5Y983",
            "display_name": "iShares Core MSCI World UCITS ETF",
            "asset_class": "Equity",
            "product_url": "https://example.test/swda",
            "holdings_url": "https://example.test/swda.csv",
            "search_text": "swda ie00b4l5y983 ishares core msci world ucits etf",
            "support_status": "supported",
            "support_reason_code": "",
            "support_error_detail": "",
        }
        entry.update(overrides)
        return entry

    def _baseline_catalog(self) -> list[dict[str, object]]:
        return [
            self._catalog_entry(),
            self._catalog_entry(
                etf_id="ishares-eimi-ie00bkm4gz66",
                symbol="EIMI",
                isin="IE00BKM4GZ66",
                display_name="iShares Core MSCI Emerging Markets IMI UCITS ETF",
                product_url="https://example.test/eimi",
                holdings_url="https://example.test/eimi.csv",
                search_text="eimi ie00bkm4gz66 ishares core msci emerging markets imi ucits etf",
            ),
            self._catalog_entry(
                etf_id="ishares-wsml-ie00bf4rfh31",
                symbol="WSML",
                isin="IE00BF4RFH31",
                display_name="iShares MSCI World Small Cap UCITS ETF",
                product_url="https://example.test/wsml",
                holdings_url="https://example.test/wsml.csv",
                search_text="wsml ie00bf4rfh31 ishares msci world small cap ucits etf",
            ),
        ]

    def test_load_saved_portfolios_returns_default_portfolio_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            portfolios = load_saved_portfolios(Path(tmpdir))

        self.assertEqual([portfolio["name"] for portfolio in portfolios], [DEFAULT_PORTFOLIO_NAME])
        self.assertEqual(
            [entry["etf_id"] for entry in portfolios[0]["entries"]],
            [
                "ishares-swda-ie00b4l5y983",
                "ishares-eimi-ie00bkm4gz66",
                "ishares-wsml-ie00bf4rfh31",
            ],
        )

    def test_load_saved_portfolios_migrates_legacy_identifier_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "user_portfolios.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "Legacy",
                            "entries": [
                                {"identifier": "SWDA", "weight_pct": 80.0},
                                {"identifier": "IE00BKM4GZ66", "weight_pct": 20.0},
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with patch(
                "src.portfolio_analysis_app.custom_portfolios.load_etf_catalog",
                return_value=self._baseline_catalog(),
            ):
                portfolios = load_saved_portfolios(data_dir)

        self.assertEqual(
            [entry["etf_id"] for entry in portfolios[0]["entries"]],
            ["ishares-swda-ie00b4l5y983", "ishares-eimi-ie00bkm4gz66"],
        )

    def test_save_saved_portfolios_persists_named_portfolios(self) -> None:
        portfolios = [
            {
                "name": "Core",
                "entries": [
                    {
                        "etf_id": "ishares-swda-ie00b4l5y983",
                        "weight_pct": 80.0,
                        "search_text": "SWDA",
                    },
                    {
                        "etf_id": "ishares-eimi-ie00bkm4gz66",
                        "weight_pct": 20.0,
                        "search_text": "EIMI",
                    },
                ],
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            save_saved_portfolios(portfolios, data_dir)
            reloaded = load_saved_portfolios(data_dir)

        self.assertEqual(reloaded, portfolios)

    def test_validate_portfolio_entries_rejects_duplicate_etf_ids_and_invalid_totals(self) -> None:
        validation = validate_portfolio_entries(
            [
                {"etf_id": "ishares-swda-ie00b4l5y983", "weight_pct": 60.0},
                {"etf_id": "ishares-swda-ie00b4l5y983", "weight_pct": 30.0},
            ]
        )

        self.assertFalse(validation["is_valid"])
        self.assertTrue(any("Duplicate ETF" in error for error in validation["errors"]))
        self.assertTrue(any("100.00%" in error for error in validation["errors"]))

    def test_resolve_portfolio_entries_reads_catalog_entries_by_etf_id(self) -> None:
        with patch(
            "src.portfolio_analysis_app.custom_portfolios.load_etf_catalog",
            return_value=self._baseline_catalog(),
        ):
            resolved = resolve_portfolio_entries(
                [
                    {"etf_id": "ishares-swda-ie00b4l5y983", "weight_pct": 78.0},
                    {"etf_id": "ishares-eimi-ie00bkm4gz66", "weight_pct": 12.0},
                ]
            )

        self.assertEqual([entry["symbol"] for entry in resolved], ["SWDA", "EIMI"])
        self.assertEqual([entry["isin"] for entry in resolved], ["IE00B4L5Y983", "IE00BKM4GZ66"])

    def test_resolve_portfolio_entries_marks_unsupported_catalog_rows(self) -> None:
        catalog = [
            self._catalog_entry(
                etf_id="ishares-bad-ie00badbad01",
                symbol="BAD",
                isin="IE00BADBAD01",
                display_name="Broken ETF",
                product_url="https://example.test/bad",
                holdings_url="",
                search_text="bad ie00badbad01 broken etf",
                support_status="unsupported",
                support_reason_code="parse_failed",
                support_error_detail="Unable to parse holdings CSV.",
            )
        ]

        with patch("src.portfolio_analysis_app.custom_portfolios.load_etf_catalog", return_value=catalog):
            resolved = resolve_portfolio_entries(
                [{"etf_id": "ishares-bad-ie00badbad01", "weight_pct": 100.0, "search_text": "Broken ETF"}]
            )

        self.assertEqual(resolved[0]["support_status"], "unsupported")
        self.assertEqual(resolved[0]["support_reason_code"], "parse_failed")
        self.assertIn("unsupported", resolved[0]["error"].lower())

    def test_validate_portfolio_entries_accepts_shape_before_resolution_blocks_analysis(self) -> None:
        validation = validate_portfolio_entries(
            [{"etf_id": "ishares-bad-ie00badbad01", "weight_pct": 100.0, "search_text": "Broken ETF"}]
        )

        self.assertTrue(validation["is_valid"])
        self.assertEqual(validation["total_weight_pct"], 100.0)

    def test_build_combined_holdings_for_portfolio_uses_latest_cached_holdings(self) -> None:
        def write_snapshot(data_dir: Path, symbol: str, date: str, company: str) -> None:
            pd.DataFrame(
                {
                    "company": [company],
                    "country": ["US"],
                    "sector": ["Technology"],
                    "asset_class": ["Equity"],
                    "holding_type": ["security"],
                    "is_cash_equivalent": [False],
                    "weight_pct": [100.0],
                }
            ).to_parquet(data_dir / f"{symbol}_{date}_holdings.parquet", index=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            write_snapshot(data_dir, "SWDA", "20260601", "Old Apple")
            write_snapshot(data_dir, "SWDA", "20260603", "Apple")
            write_snapshot(data_dir, "EIMI", "20260602", "Tencent")
            write_snapshot(data_dir, "WSML", "20260601", "Small Cap Co")

            with patch(
                "src.portfolio_analysis_app.custom_portfolios.load_etf_catalog",
                return_value=self._baseline_catalog(),
            ):
                entries = resolve_portfolio_entries(
                    [
                        {"etf_id": "ishares-swda-ie00b4l5y983", "weight_pct": 78.0},
                        {"etf_id": "ishares-eimi-ie00bkm4gz66", "weight_pct": 12.0},
                        {"etf_id": "ishares-wsml-ie00bf4rfh31", "weight_pct": 10.0},
                    ]
                )
                result = build_combined_holdings_for_portfolio(entries, data_dir=data_dir)

        self.assertEqual(result["snapshot_label"], "Mixed cached snapshots")
        self.assertEqual(set(result["combined_holdings"]["parent_etf"]), {"SWDA", "EIMI", "WSML"})
        self.assertIn("Apple", result["combined_holdings"]["company"].tolist())
        self.assertNotIn("Old Apple", result["combined_holdings"]["company"].tolist())
        self.assertAlmostEqual(result["combined_holdings"]["contribution_pct"].sum(), 100.0, places=2)

    def test_refresh_supported_etf_snapshot_passes_issuer_and_holdings_url_to_retrieval(self) -> None:
        holdings = pd.DataFrame(
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
        validation = object()
        calls: list[dict[str, object]] = []

        class FakeDataRetrival:
            TODAY = "20260603"

            class ETF:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)

            @staticmethod
            def fetch_standardised_holdings_snapshot(**kwargs):
                calls.append(kwargs)
                return holdings, validation, "https://example.test/vwrp.csv"

            @staticmethod
            def save_etf_outputs(etf, saved_holdings, meta, saved_validation, raw_csv_path):
                calls.append(
                    {
                        "saved_etf": etf,
                        "saved_holdings": saved_holdings,
                        "saved_validation": saved_validation,
                        "raw_csv_path": raw_csv_path,
                    }
                )

        with patch.dict("sys.modules", {"src.portfolio_analysis_app.data_retrival": FakeDataRetrival}):
            result = refresh_supported_etf_snapshot(
                {
                    "symbol": "VWRP",
                    "isin": "IE00BK5BQT80",
                    "product_page": "https://example.test/vwrp",
                    "holdings_url": "https://example.test/vwrp.csv",
                    "issuer": "vanguard",
                    "weight_pct": 25.0,
                    "error": "",
                }
            )

        self.assertEqual(
            calls[0],
            {
                "symbol": "VWRP",
                "isin": "IE00BK5BQT80",
                "product_page": "https://example.test/vwrp",
                "pie_weight": 0.25,
                "issuer_key": "vanguard",
                "holdings_url": "https://example.test/vwrp.csv",
            },
        )
        self.assertEqual(result["symbol"], "VWRP")
        self.assertEqual(result["snapshot_date"], "20260603")
