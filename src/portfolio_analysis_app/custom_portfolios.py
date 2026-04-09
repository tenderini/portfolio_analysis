from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .portfolio_analysis import format_snapshot_date


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SAVED_PORTFOLIOS_FILENAME = "user_portfolios.json"
DEFAULT_PORTFOLIO_NAME = "PIE Default"
WEIGHT_TOTAL_TOLERANCE = 1e-6
SNAPSHOT_PATTERN = re.compile(r"^(?P<symbol>[A-Z0-9._-]+)_(?P<date>\d{8})_holdings\.parquet$")

SUPPORTED_ETF_DEFINITIONS = {
    "SWDA": {
        "symbol": "SWDA",
        "isin": "IE00B4L5Y983",
        "display_name": "iShares Core MSCI World UCITS ETF",
        "product_page": "https://www.blackrock.com/uk/individual/products/251882/ishares-msci-world-ucits-etf-acc-fund",
        "issuer": "iShares/BlackRock",
    },
    "EMIM": {
        "symbol": "EMIM",
        "isin": "IE00BKM4GZ66",
        "display_name": "iShares Core MSCI Emerging Markets IMI UCITS ETF",
        "product_page": "https://www.blackrock.com/uk/individual/products/264659/ishares-msci-emerging-markets-imi-ucits-etf",
        "issuer": "iShares/BlackRock",
    },
    "WSML": {
        "symbol": "WSML",
        "isin": "IE00BF4RFH31",
        "display_name": "iShares MSCI World Small Cap UCITS ETF",
        "product_page": "https://www.blackrock.com/uk/individual/products/296576/ishares-msci-world-small-cap-ucits-etf",
        "issuer": "iShares/BlackRock",
    },
}


def get_default_saved_portfolios() -> list[dict[str, Any]]:
    return [
        {
            "name": DEFAULT_PORTFOLIO_NAME,
            "entries": [
                {"identifier": "SWDA", "weight_pct": 78.0},
                {"identifier": "EMIM", "weight_pct": 12.0},
                {"identifier": "WSML", "weight_pct": 10.0},
            ],
        }
    ]


def load_saved_portfolios(data_dir: Path | str = DATA_DIR) -> list[dict[str, Any]]:
    storage_path = _portfolio_storage_path(data_dir)
    if not storage_path.exists():
        return get_default_saved_portfolios()

    raw_data = json.loads(storage_path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, list):
        return get_default_saved_portfolios()
    return raw_data


def save_saved_portfolios(portfolios: list[dict[str, Any]], data_dir: Path | str = DATA_DIR) -> None:
    storage_path = _portfolio_storage_path(data_dir)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(json.dumps(portfolios, indent=2), encoding="utf-8")


def resolve_portfolio_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved_entries: list[dict[str, Any]] = []
    for entry in entries:
        identifier = str(entry.get("identifier", "")).strip()
        normalized_identifier = _normalize_identifier(identifier)
        definition = _lookup_supported_definition(normalized_identifier)
        resolved_entry = {
            "identifier": identifier,
            "weight_pct": float(entry.get("weight_pct", 0.0) or 0.0),
            "symbol": "",
            "isin": "",
            "display_name": "",
            "product_page": "",
            "issuer": "",
            "is_supported": definition is not None,
            "error": "",
        }
        if definition is None:
            resolved_entry["error"] = f'Unsupported ETF identifier: "{identifier}"'
        else:
            resolved_entry.update(definition)
        resolved_entries.append(resolved_entry)
    return resolved_entries


def validate_portfolio_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    seen_identifiers: set[str] = set()
    total_weight_pct = 0.0

    for entry in entries:
        identifier = str(entry.get("identifier", "")).strip()
        normalized_identifier = _normalize_identifier(identifier)
        raw_weight = entry.get("weight_pct", 0.0)

        if not identifier:
            errors.append("ETF identifier is required.")
            continue

        if normalized_identifier in seen_identifiers:
            errors.append(f'Duplicate ETF identifier: "{identifier}".')
        else:
            seen_identifiers.add(normalized_identifier)

        try:
            weight_pct = float(raw_weight)
        except (TypeError, ValueError):
            errors.append(f'Weight for "{identifier}" must be numeric.')
            continue

        if weight_pct <= 0:
            errors.append(f'Weight for "{identifier}" must be positive.')
            continue

        total_weight_pct += weight_pct

    if abs(total_weight_pct - 100.0) > WEIGHT_TOTAL_TOLERANCE:
        errors.append(
            f"Portfolio weights must sum to 100.00%. Current total: {total_weight_pct:.2f}%."
        )

    return {
        "is_valid": not errors,
        "errors": errors,
        "total_weight_pct": total_weight_pct,
    }


def build_combined_holdings_for_portfolio(
    entries: list[dict[str, Any]],
    data_dir: Path | str = DATA_DIR,
) -> dict[str, Any]:
    data_path = Path(data_dir)
    resolved_entries = resolve_portfolio_entries(entries)
    unsupported = [entry["error"] for entry in resolved_entries if entry["error"]]
    if unsupported:
        raise ValueError("; ".join(unsupported))

    combined_frames: list[pd.DataFrame] = []
    snapshot_dates: set[str] = set()
    etf_descriptions: list[dict[str, str]] = []

    for entry in resolved_entries:
        symbol = str(entry["symbol"])
        snapshot_date = _get_latest_holdings_snapshot_date(symbol, data_path)
        if snapshot_date is None:
            raise FileNotFoundError(f"No cached holdings snapshot found for {symbol}")

        snapshot_dates.add(snapshot_date)
        holdings_path = data_path / f"{symbol}_{snapshot_date}_holdings.parquet"
        holdings = pd.read_parquet(holdings_path).copy()
        holdings["weight_pct"] = pd.to_numeric(holdings["weight_pct"], errors="coerce").fillna(0.0)

        allocation_fraction = float(entry["weight_pct"]) / 100.0
        holdings["pie_weight"] = allocation_fraction
        holdings["contribution_pct"] = holdings["weight_pct"] * allocation_fraction
        holdings["parent_etf"] = symbol
        combined_frames.append(holdings)
        etf_descriptions.append(
            {
                "ticker": symbol,
                "description": str(entry["display_name"]),
                "role": f'Selected portfolio allocation: {float(entry["weight_pct"]):.2f}%.',
            }
        )

    if not combined_frames:
        combined_holdings = pd.DataFrame()
    else:
        combined_holdings = pd.concat(combined_frames, ignore_index=True)
        combined_holdings = combined_holdings.sort_values(
            ["contribution_pct", "parent_etf", "company"],
            ascending=[False, True, True],
        ).reset_index(drop=True)

    snapshot_label = (
        format_snapshot_date(next(iter(snapshot_dates)))
        if len(snapshot_dates) == 1
        else "Mixed cached snapshots"
    )
    return {
        "combined_holdings": combined_holdings,
        "snapshot_label": snapshot_label,
        "etf_descriptions": etf_descriptions,
    }


def refresh_supported_etf_snapshot(
    entry: dict[str, Any],
    data_dir: Path | str = DATA_DIR,
) -> dict[str, Any]:
    if entry.get("error"):
        raise ValueError(str(entry["error"]))

    try:
        from . import data_retrival
    except Exception as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError(
            "Refreshing ETF snapshots requires the optional Playwright-based retrieval dependencies."
        ) from exc

    symbol = str(entry.get("symbol", "")).strip()
    isin = str(entry.get("isin", "")).strip()
    product_page = str(entry.get("product_page", "")).strip()
    if not symbol or not isin or not product_page:
        raise ValueError("Cannot refresh an ETF snapshot without symbol, ISIN, and product page metadata.")

    etf = data_retrival.ETF(
        symbol=symbol,
        isin=isin,
        product_page=product_page,
        pie_weight=float(entry.get("weight_pct", 0.0)) / 100.0,
    )

    html, request_context, context, browser, playwright_instance = data_retrival.fetch_rendered_html_and_request_ctx(
        etf.product_page
    )
    try:
        csv_url = data_retrival.extract_holdings_csv_url(etf.product_page, html)
        csv_text = data_retrival.download_csv_via_playwright(
            request_context,
            csv_url,
            referer=etf.product_page,
        )
        raw_csv_path = data_retrival.save_raw_csv_output(etf, csv_text)
        raw_df = data_retrival.parse_holdings_csv(csv_text)
        holdings = data_retrival.standardise_holdings(raw_df)
        validation = data_retrival.validate_holdings_capture(raw_df, holdings)
        data_retrival.save_etf_outputs(etf, holdings, {"etfs": {}}, validation, raw_csv_path)
    finally:  # pragma: no cover - runtime/network path
        data_retrival.close_playwright(context, browser, playwright_instance)

    return {
        "symbol": symbol,
        "snapshot_date": data_retrival.TODAY,
        "holdings_rows": int(len(holdings)),
    }


def _portfolio_storage_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / SAVED_PORTFOLIOS_FILENAME


def _normalize_identifier(identifier: str) -> str:
    return identifier.strip().upper()


def _lookup_supported_definition(identifier: str) -> dict[str, str] | None:
    if identifier in SUPPORTED_ETF_DEFINITIONS:
        return SUPPORTED_ETF_DEFINITIONS[identifier].copy()

    for definition in SUPPORTED_ETF_DEFINITIONS.values():
        if identifier == definition["isin"].upper():
            return definition.copy()
    return None


def _get_latest_holdings_snapshot_date(symbol: str, data_dir: Path) -> str | None:
    dates: list[str] = []
    for file_path in data_dir.glob(f"{symbol}_*_holdings.parquet"):
        match = SNAPSHOT_PATTERN.match(file_path.name)
        if match and match.group("symbol") == symbol:
            dates.append(match.group("date"))

    if not dates:
        return None
    return sorted(dates, reverse=True)[0]
