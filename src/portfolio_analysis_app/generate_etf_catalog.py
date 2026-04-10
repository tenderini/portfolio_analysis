from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

from .data_retrival import (
    close_playwright,
    fetch_rendered_html_and_request_ctx,
    fetch_standardised_holdings_snapshot,
)
from .etf_catalog import DEFAULT_ETF_CATALOG_PATH, load_etf_catalog


DISCOVERY_URL = "https://www.ishares.com/uk/individual/en/products/product-list"
DISCOVERY_BASE_URL = "https://www.ishares.com"


def normalise_catalog_candidate(candidate: dict[str, Any]) -> dict[str, str]:
    symbol = str(candidate.get("symbol", "")).strip().upper()
    isin = str(candidate.get("isin", "")).strip().upper()
    display_name = str(candidate.get("display_name", "")).strip()
    asset_class = str(candidate.get("asset_class", "")).strip() or "Unknown"
    product_url = str(candidate.get("product_url", "")).strip()
    holdings_url = str(candidate.get("holdings_url", "")).strip()
    etf_id = f"ishares-{symbol.lower()}-{isin.lower()}"
    search_text = " ".join(
        part for part in [symbol.lower(), isin.lower(), display_name.casefold()] if part
    ).strip()
    return {
        "etf_id": etf_id,
        "issuer_key": "ishares",
        "symbol": symbol,
        "isin": isin,
        "display_name": display_name,
        "asset_class": asset_class,
        "product_url": product_url,
        "holdings_url": holdings_url,
        "search_text": re.sub(r"\s+", " ", search_text),
    }


def build_supported_catalog(
    candidates: list[dict[str, Any]],
    validator: Callable[[dict[str, Any]], tuple[bool, str]] | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    validate = validator or _validate_candidate_support
    accepted: list[dict[str, str]] = []
    rejected = Counter()
    seen_isins: set[str] = set()

    for raw_candidate in candidates:
        candidate = normalise_catalog_candidate(raw_candidate)
        if not candidate["isin"]:
            rejected["missing_isin"] += 1
            continue
        if candidate["isin"] in seen_isins:
            rejected["duplicate_isin"] += 1
            continue

        is_supported, reason = validate(candidate)
        if not is_supported:
            rejected[reason or "validation_failed"] += 1
            continue

        seen_isins.add(candidate["isin"])
        accepted.append(candidate)

    accepted.sort(key=lambda entry: (entry["display_name"], entry["symbol"]))
    return accepted, {
        "discovered": len(candidates),
        "accepted": len(accepted),
        "rejected": dict(rejected),
    }


def write_catalog(
    catalog: list[dict[str, str]],
    output_path: Path | str = DEFAULT_ETF_CATALOG_PATH,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(catalog, key=lambda entry: (entry["display_name"], entry["symbol"]))
    path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")


def discover_ishares_candidates() -> list[dict[str, str]]:
    html, _, context, browser, playwright_instance = fetch_rendered_html_and_request_ctx(DISCOVERY_URL)
    try:
        pattern = re.compile(
            r'data-product-ticker="(?P<symbol>[^"]+)".*?data-product-isin="(?P<isin>[^"]+)".*?href="(?P<product_url>/[^"]+)"',
            re.IGNORECASE | re.DOTALL,
        )
        candidates: dict[tuple[str, str], dict[str, str]] = {}
        for match in pattern.finditer(html):
            symbol = match.group("symbol").strip().upper()
            isin = match.group("isin").strip().upper()
            product_url = urljoin(DISCOVERY_BASE_URL, match.group("product_url").strip())
            candidates[(symbol, isin)] = {
                "symbol": symbol,
                "isin": isin,
                "display_name": symbol,
                "asset_class": "Unknown",
                "product_url": product_url,
                "holdings_url": "",
            }
        if candidates:
            return sorted(candidates.values(), key=lambda entry: (entry["symbol"], entry["isin"]))

        # Fallback to the currently committed catalogue when the product-list markup changes.
        fallback_catalog = load_etf_catalog(DEFAULT_ETF_CATALOG_PATH)
        if fallback_catalog:
            return [
                {
                    "symbol": entry["symbol"],
                    "isin": entry["isin"],
                    "display_name": entry["display_name"],
                    "asset_class": entry["asset_class"],
                    "product_url": entry["product_url"],
                    "holdings_url": entry["holdings_url"],
                }
                for entry in fallback_catalog
            ]

        raise ValueError("No ETF candidates were discovered from the iShares product list page.")
    finally:
        close_playwright(context, browser, playwright_instance)


def main() -> None:
    candidates = discover_ishares_candidates()
    catalog, report = build_supported_catalog(candidates)
    write_catalog(catalog, DEFAULT_ETF_CATALOG_PATH)
    print(json.dumps(report, indent=2))


def _validate_candidate_support(candidate: dict[str, Any]) -> tuple[bool, str]:
    try:
        holdings, validation, holdings_url = fetch_standardised_holdings_snapshot(
            symbol=candidate["symbol"],
            isin=candidate["isin"],
            product_page=candidate["product_url"],
        )
    except Exception as exc:
        return False, str(exc)

    if holdings.empty:
        return False, "empty_holdings"
    if not validation.positive_weight_sum_in_expected_band:
        return False, "weight_sum_out_of_band"

    candidate["holdings_url"] = holdings_url
    return True, ""


if __name__ == "__main__":
    main()
