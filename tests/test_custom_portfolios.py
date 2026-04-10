import json
import tempfile
import unittest
from pathlib import Path

from src.portfolio_analysis_app.custom_portfolios import (
    DEFAULT_PORTFOLIO_NAME,
    build_combined_holdings_for_portfolio,
    load_saved_portfolios,
    resolve_portfolio_entries,
    save_saved_portfolios,
    validate_portfolio_entries,
)


class SavedPortfolioTests(unittest.TestCase):
    def test_load_saved_portfolios_returns_default_portfolio_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            portfolios = load_saved_portfolios(Path(tmpdir))

        self.assertEqual([portfolio["name"] for portfolio in portfolios], [DEFAULT_PORTFOLIO_NAME])
        self.assertEqual(
            [entry["etf_id"] for entry in portfolios[0]["entries"]],
            [
                "ishares-swda-ie00b4l5y983",
                "ishares-emim-ie00bkm4gz66",
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

            portfolios = load_saved_portfolios(data_dir)

        self.assertEqual(
            [entry["etf_id"] for entry in portfolios[0]["entries"]],
            ["ishares-swda-ie00b4l5y983", "ishares-emim-ie00bkm4gz66"],
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
                        "etf_id": "ishares-emim-ie00bkm4gz66",
                        "weight_pct": 20.0,
                        "search_text": "EMIM",
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
        resolved = resolve_portfolio_entries(
            [
                {"etf_id": "ishares-swda-ie00b4l5y983", "weight_pct": 78.0},
                {"etf_id": "ishares-emim-ie00bkm4gz66", "weight_pct": 12.0},
            ]
        )

        self.assertEqual([entry["symbol"] for entry in resolved], ["SWDA", "EMIM"])
        self.assertEqual([entry["isin"] for entry in resolved], ["IE00B4L5Y983", "IE00BKM4GZ66"])

    def test_build_combined_holdings_for_portfolio_uses_latest_cached_holdings(self) -> None:
        entries = resolve_portfolio_entries(
            [
                {"etf_id": "ishares-swda-ie00b4l5y983", "weight_pct": 78.0},
                {"etf_id": "ishares-emim-ie00bkm4gz66", "weight_pct": 12.0},
                {"etf_id": "ishares-wsml-ie00bf4rfh31", "weight_pct": 10.0},
            ]
        )

        result = build_combined_holdings_for_portfolio(entries, data_dir=Path("data"))

        self.assertEqual(result["snapshot_label"], "Apr 8, 2026")
        self.assertEqual(set(result["combined_holdings"]["parent_etf"]), {"SWDA", "EMIM", "WSML"})
        self.assertAlmostEqual(result["combined_holdings"]["contribution_pct"].sum(), 99.92, places=2)
