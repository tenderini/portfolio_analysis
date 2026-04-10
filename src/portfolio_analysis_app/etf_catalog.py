from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .portfolio_analysis import format_snapshot_date


PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data"
DEFAULT_ETF_CATALOG_PATH = PACKAGE_DIR / "data" / "etf_catalog.json"
SNAPSHOT_PATTERN = re.compile(r"^(?P<symbol>[A-Z0-9._-]+)_(?P<date>\d{8})_holdings\.parquet$")
REQUIRED_CATALOG_FIELDS = {
    "etf_id",
    "issuer_key",
    "symbol",
    "isin",
    "display_name",
    "asset_class",
    "product_url",
    "holdings_url",
    "search_text",
    "support_status",
    "support_reason_code",
    "support_error_detail",
}


def _validate_support_fields(entry: dict[str, Any], index: int) -> None:
    status = str(entry["support_status"]).strip()
    reason_code = str(entry["support_reason_code"]).strip()

    if status not in {"supported", "unsupported"}:
        raise ValueError(f'ETF catalogue entry {index} has invalid support_status: "{status}".')
    if status == "supported" and reason_code:
        raise ValueError(f'ETF catalogue entry {index} is supported but has a support_reason_code: "{reason_code}".')
    if status == "unsupported" and not reason_code:
        raise ValueError(f"ETF catalogue entry {index} is unsupported but missing support_reason_code.")


def load_etf_catalog(catalog_path: Path | str = DEFAULT_ETF_CATALOG_PATH) -> list[dict[str, Any]]:
    path = Path(catalog_path)
    raw_data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, list):
        raise ValueError("ETF catalogue must contain a list of ETF objects.")

    catalog: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_isins: set[str] = set()
    for index, raw_entry in enumerate(raw_data, start=1):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"ETF catalogue entry {index} must be an object.")

        missing_fields = sorted(REQUIRED_CATALOG_FIELDS.difference(raw_entry))
        if missing_fields:
            raise ValueError(
                f"ETF catalogue entry {index} is missing required fields: {', '.join(missing_fields)}"
            )

        entry = {
            "etf_id": str(raw_entry["etf_id"]).strip(),
            "issuer_key": str(raw_entry["issuer_key"]).strip(),
            "symbol": str(raw_entry["symbol"]).strip().upper(),
            "isin": str(raw_entry["isin"]).strip().upper(),
            "display_name": str(raw_entry["display_name"]).strip(),
            "asset_class": str(raw_entry["asset_class"]).strip(),
            "product_url": str(raw_entry["product_url"]).strip(),
            "holdings_url": str(raw_entry["holdings_url"]).strip(),
            "search_text": re.sub(r"\s+", " ", str(raw_entry["search_text"]).strip().casefold()),
            "support_status": str(raw_entry["support_status"]).strip(),
            "support_reason_code": str(raw_entry["support_reason_code"]).strip(),
            "support_error_detail": str(raw_entry["support_error_detail"]).strip(),
        }
        if not entry["etf_id"]:
            raise ValueError(f"ETF catalogue entry {index} has an empty etf_id.")
        if entry["etf_id"] in seen_ids:
            raise ValueError(f'Duplicate ETF catalogue etf_id: "{entry["etf_id"]}".')
        if entry["isin"] in seen_isins:
            raise ValueError(f'Duplicate ETF catalogue ISIN: "{entry["isin"]}".')
        _validate_support_fields(entry, index)

        seen_ids.add(entry["etf_id"])
        seen_isins.add(entry["isin"])
        catalog.append(entry)

    return sorted(catalog, key=lambda item: (item["display_name"], item["symbol"]))


def find_exact_catalog_match(
    value: str,
    catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    needle = str(value).strip().upper()
    if not needle:
        return None

    entries = catalog or load_etf_catalog()
    for entry in entries:
        if needle in {entry["etf_id"].upper(), entry["symbol"], entry["isin"]}:
            return entry
    return None


def search_etf_catalog(
    query: str,
    catalog: list[dict[str, Any]] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    needle = re.sub(r"\s+", " ", str(query).strip().casefold())
    entries = catalog or load_etf_catalog()
    if not needle:
        return entries[:limit]

    matches = [
        entry
        for entry in entries
        if needle in entry["search_text"]
        or needle in entry["symbol"].casefold()
        or needle in entry["isin"].casefold()
    ]
    return matches[:limit]


def build_catalog_dataframe(
    catalog: list[dict[str, Any]] | None = None,
    data_dir: Path | str = DEFAULT_DATA_DIR,
) -> pd.DataFrame:
    entries = catalog or load_etf_catalog()
    data_path = Path(data_dir)
    rows = [
        {
            "symbol": entry["symbol"],
            "isin": entry["isin"],
            "display_name": entry["display_name"],
            "asset_class": entry["asset_class"],
            "support_status": entry["support_status"],
            "support_reason_code": entry["support_reason_code"],
            "cached_snapshot": _find_latest_snapshot_label(entry["symbol"], data_path),
        }
        for entry in entries
    ]
    return pd.DataFrame(rows)


def _find_latest_snapshot_label(symbol: str, data_dir: Path) -> str:
    snapshot_dates: list[str] = []
    for file_path in data_dir.glob(f"{symbol}_*_holdings.parquet"):
        match = SNAPSHOT_PATTERN.match(file_path.name)
        if match and match.group("symbol") == symbol:
            snapshot_dates.append(match.group("date"))

    if not snapshot_dates:
        return "Not cached"
    return format_snapshot_date(max(snapshot_dates))
