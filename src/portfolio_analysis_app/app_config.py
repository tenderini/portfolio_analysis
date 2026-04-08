from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


@dataclass(frozen=True)
class UIConfig:
    show_portfolio_total_in_overview: bool = False
    top_n: int = 20


@dataclass(frozen=True)
class ContentConfig:
    page_title: str = "PIE Portfolio Analysis"
    dashboard_title: str = "PIE Portfolio Look-Through Dashboard"
    snapshot_description_template: str = (
        "Snapshot <strong>{snapshot_date}</strong> with drilldowns across companies, "
        "countries, sectors, and cross-ETF overlap."
    )


@dataclass(frozen=True)
class AppConfig:
    ui: UIConfig = field(default_factory=UIConfig)
    content: ContentConfig = field(default_factory=ContentConfig)


DEFAULT_CONFIG = AppConfig()
REPO_ROOT = Path(__file__).resolve().parents[2]


def load_app_config(path: Path | None = None) -> AppConfig:
    config_path = path or REPO_ROOT / "config.toml"
    if not config_path.exists():
        return DEFAULT_CONFIG

    loaded = _load_toml(config_path.read_text(encoding="utf-8"))
    ui = _read_table(loaded, "ui")
    content = _read_table(loaded, "content")

    return AppConfig(
        ui=replace(
            DEFAULT_CONFIG.ui,
            show_portfolio_total_in_overview=bool(
                ui.get(
                    "show_portfolio_total_in_overview",
                    DEFAULT_CONFIG.ui.show_portfolio_total_in_overview,
                )
            ),
            top_n=int(ui.get("top_n", DEFAULT_CONFIG.ui.top_n)),
        ),
        content=replace(
            DEFAULT_CONFIG.content,
            page_title=str(content.get("page_title", DEFAULT_CONFIG.content.page_title)),
            dashboard_title=str(
                content.get("dashboard_title", DEFAULT_CONFIG.content.dashboard_title)
            ),
            snapshot_description_template=str(
                content.get(
                    "snapshot_description_template",
                    DEFAULT_CONFIG.content.snapshot_description_template,
                )
            ),
        ),
    )


def _read_table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def _load_toml(raw_text: str) -> dict[str, Any]:
    if tomllib is not None:
        return tomllib.loads(raw_text)
    return _parse_simple_toml(raw_text)


def _parse_simple_toml(raw_text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_section = data

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            current_section = data.setdefault(section_name, {})
            continue

        key, separator, value = line.partition("=")
        if not separator:
            continue

        current_section[key.strip()] = _parse_toml_value(value.strip())

    return data


def _parse_toml_value(value: str) -> Any:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value
