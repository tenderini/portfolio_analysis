from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .etf_catalog import find_exact_catalog_match, load_etf_catalog
from .portfolio_analysis import format_snapshot_date


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SAVED_PORTFOLIOS_FILENAME = "user_portfolios.json"
DEFAULT_PORTFOLIO_NAME = "PIE Default"
WEIGHT_TOTAL_TOLERANCE = 1e-6
SNAPSHOT_PATTERN = re.compile(r"^(?P<symbol>[A-Z0-9._-]+)_(?P<date>\d{8})_holdings\.parquet$")


def get_default_saved_portfolios() -> list[dict[str, Any]]:
    return [
        {
            "name": DEFAULT_PORTFOLIO_NAME,
            "entries": [
                {
                    "etf_id": "ishares-swda-ie00b4l5y983",
                    "weight_pct": 78.0,
                    "search_text": "SWDA",
                },
                {
                    "etf_id": "ishares-emim-ie00bkm4gz66",
                    "weight_pct": 12.0,
                    "search_text": "EMIM",
                },
                {
                    "etf_id": "ishares-wsml-ie00bf4rfh31",
                    "weight_pct": 10.0,
                    "search_text": "WSML",
                },
            ],
        }
    ]


def load_saved_portfolios(data_dir: Path | str = DATA_DIR) -> list[dict[str, Any]]:
    catalog = load_etf_catalog()
    storage_path = _portfolio_storage_path(data_dir)
    if not storage_path.exists():
        return get_default_saved_portfolios()

    raw_data = json.loads(storage_path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, list):
        return get_default_saved_portfolios()

    migrated_portfolios: list[dict[str, Any]] = []
    for raw_portfolio in raw_data:
        entries = raw_portfolio.get("entries", [])
        migrated_portfolios.append(
            {
                "name": str(raw_portfolio.get("name", DEFAULT_PORTFOLIO_NAME)),
                "entries": [_migrate_saved_entry(entry, catalog) for entry in entries],
            }
        )
    return migrated_portfolios or get_default_saved_portfolios()


def save_saved_portfolios(portfolios: list[dict[str, Any]], data_dir: Path | str = DATA_DIR) -> None:
    normalised_portfolios = [
        {
            "name": str(portfolio.get("name", DEFAULT_PORTFOLIO_NAME)),
            "entries": [_normalise_saved_entry(entry) for entry in portfolio.get("entries", [])],
        }
        for portfolio in portfolios
    ]
    storage_path = _portfolio_storage_path(data_dir)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(json.dumps(normalised_portfolios, indent=2), encoding="utf-8")


def resolve_portfolio_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog = load_etf_catalog()
    catalog_by_id = {entry["etf_id"]: entry for entry in catalog}
    resolved_entries: list[dict[str, Any]] = []

    for entry in entries:
        etf_id = str(entry.get("etf_id", "")).strip()
        catalog_entry = catalog_by_id.get(etf_id)
        resolved_entry = {
            "etf_id": etf_id,
            "search_text": str(entry.get("search_text", "")),
            "weight_pct": float(entry.get("weight_pct", 0.0) or 0.0),
            "symbol": "",
            "isin": "",
            "display_name": "",
            "asset_class": "",
            "product_page": "",
            "holdings_url": "",
            "issuer": "",
            "is_supported": False,
            "support_status": "",
            "support_reason_code": "",
            "support_error_detail": "",
            "error": "",
        }
        if catalog_entry is None:
            resolved_entry["error"] = f'Unsupported ETF ID: "{etf_id}"'
        else:
            resolved_entry.update(
                {
                    "symbol": catalog_entry["symbol"],
                    "isin": catalog_entry["isin"],
                    "display_name": catalog_entry["display_name"],
                    "asset_class": catalog_entry["asset_class"],
                    "product_page": catalog_entry["product_url"],
                    "holdings_url": catalog_entry["holdings_url"],
                    "issuer": catalog_entry["issuer_key"],
                    "is_supported": catalog_entry["support_status"] == "supported",
                    "support_status": catalog_entry["support_status"],
                    "support_reason_code": catalog_entry["support_reason_code"],
                    "support_error_detail": catalog_entry["support_error_detail"],
                }
            )
            if catalog_entry["support_status"] != "supported":
                resolved_entry["error"] = (
                    f'Unsupported ETF: "{catalog_entry["display_name"]}" '
                    f'({catalog_entry["support_reason_code"]}).'
                )
        resolved_entries.append(resolved_entry)
    return resolved_entries


def validate_portfolio_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    total_weight_pct = 0.0

    for entry in entries:
        etf_id = str(entry.get("etf_id", "")).strip()
        label = etf_id or str(entry.get("search_text", "")).strip() or "ETF"
        raw_weight = entry.get("weight_pct", 0.0)

        if not etf_id:
            errors.append("ETF selection is required.")
            continue

        if etf_id in seen_ids:
            errors.append(f'Duplicate ETF entry: "{etf_id}".')
        else:
            seen_ids.add(etf_id)

        try:
            weight_pct = float(raw_weight)
        except (TypeError, ValueError):
            errors.append(f'Weight for "{label}" must be numeric.')
            continue

        if weight_pct <= 0:
            errors.append(f'Weight for "{label}" must be positive.')
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


def _normalise_saved_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "etf_id": str(entry.get("etf_id", "")).strip(),
        "weight_pct": float(entry.get("weight_pct", 0.0) or 0.0),
        "search_text": str(entry.get("search_text", "")),
    }


def _migrate_saved_entry(entry: dict[str, Any], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    if entry.get("etf_id"):
        return _normalise_saved_entry(entry)

    legacy_identifier = str(entry.get("identifier", "")).strip()
    match = find_exact_catalog_match(legacy_identifier, catalog)
    return {
        "etf_id": "" if match is None else str(match["etf_id"]),
        "weight_pct": float(entry.get("weight_pct", 0.0) or 0.0),
        "search_text": legacy_identifier,
    }


def _get_latest_holdings_snapshot_date(symbol: str, data_dir: Path) -> str | None:
    dates: list[str] = []
    for file_path in data_dir.glob(f"{symbol}_*_holdings.parquet"):
        match = SNAPSHOT_PATTERN.match(file_path.name)
        if match and match.group("symbol") == symbol:
            dates.append(match.group("date"))

    if not dates:
        return None
    return sorted(dates, reverse=True)[0]
