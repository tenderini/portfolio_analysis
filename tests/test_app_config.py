from pathlib import Path
import unittest


class AppConfigTests(unittest.TestCase):
    def test_load_app_config_returns_defaults_when_file_is_missing(self) -> None:
        from app_config import DEFAULT_CONFIG, load_app_config

        config = load_app_config(Path("tests/fixtures/does-not-exist.toml"))

        self.assertEqual(config.ui.top_n, DEFAULT_CONFIG.ui.top_n)
        self.assertFalse(config.ui.show_portfolio_total_in_overview)
        self.assertEqual(config.content.page_title, DEFAULT_CONFIG.content.page_title)
        self.assertEqual(config.content.dashboard_title, DEFAULT_CONFIG.content.dashboard_title)

    def test_load_app_config_reads_values_from_toml(self) -> None:
        from app_config import load_app_config

        fixture = Path("tests/tmp_config.toml")
        fixture.write_text(
            "\n".join(
                [
                    "[ui]",
                    "show_portfolio_total_in_overview = true",
                    "top_n = 12",
                    "",
                    "[content]",
                    'page_title = "Custom Title"',
                    'dashboard_title = "Custom Dashboard"',
                    'snapshot_description_template = "Snapshot {snapshot_date} custom"',
                ]
            ),
            encoding="utf-8",
        )
        self.addCleanup(lambda: fixture.unlink(missing_ok=True))

        config = load_app_config(fixture)

        self.assertTrue(config.ui.show_portfolio_total_in_overview)
        self.assertEqual(config.ui.top_n, 12)
        self.assertEqual(config.content.page_title, "Custom Title")
        self.assertEqual(config.content.dashboard_title, "Custom Dashboard")
        self.assertEqual(
            config.content.snapshot_description_template,
            "Snapshot {snapshot_date} custom",
        )
