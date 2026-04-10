from __future__ import annotations

import html as html_lib
import json
import logging
import re
import sys
from time import perf_counter
from collections import Counter
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from src.portfolio_analysis_app.app_config import load_app_config
    from src.portfolio_analysis_app.data_retrival import (
        HEADERS_UA,
        accept_cookies_best_effort,
        close_playwright,
        fetch_rendered_html_and_request_ctx,
        fetch_standardised_holdings_snapshot,
    )
    from src.portfolio_analysis_app.etf_catalog import DEFAULT_ETF_CATALOG_PATH, load_etf_catalog
else:
    from .app_config import load_app_config
    from .data_retrival import (
        HEADERS_UA,
        accept_cookies_best_effort,
        close_playwright,
        fetch_rendered_html_and_request_ctx,
        fetch_standardised_holdings_snapshot,
    )
    from .etf_catalog import DEFAULT_ETF_CATALOG_PATH, load_etf_catalog

from playwright.sync_api import sync_playwright


DISCOVERY_URL_TEMPLATE = (
    "https://www.ishares.com/uk/individual/en/products/etf-investments"
    "?switchLocale=y&siteEntryPassthrough=true"
    "#/?productView=etf&pageNumber={page_number}&sortColumn=totalFundSizeInMillions"
    "&sortDirection=desc&dataView=keyFacts&keyFacts=all"
)
DISCOVERY_BASE_URL = "https://www.ishares.com"
MAX_DISCOVERY_PAGES = 4
DISCOVERY_CANDIDATE_LIMIT = 10
PRODUCT_URL_PATTERN = re.compile(
    r'(?P<product_url>(?:https?://www\.ishares\.com)?/uk/individual/en/products/[^"\'\\<>\s]+)',
    re.IGNORECASE,
)
DISCOVERY_TABLE_ROW_PATTERN = re.compile(
    r'<tr>\s*'
    r'<td class="links"><a href="(?P<product_url>/uk/individual/en/products/[^"]+)">(?P<symbol>[^<]+)</a></td>\s*'
    r'<td class="links"><a href="/uk/individual/en/products/[^"]+">(?P<display_name>[^<]+)</a></td>'
    r'(?P<rest>.*?)</tr>',
    re.IGNORECASE | re.DOTALL,
)
DATA_PRODUCT_PATTERN = re.compile(
    r'data-product-ticker="(?P<symbol>[^"]+)".*?data-product-isin="(?P<isin>[^"]+)".*?href="(?P<product_url>/[^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
DISCOVERY_TEXT_LINK_PATTERN = re.compile(
    r'<a[^>]+href="(?P<product_url>/[^"]*/products/[^"]+)"[^>]*>\s*Explore\s+(?P<symbol>[A-Z0-9._-]+)\s+on\s+the\s+product\s+page',
    re.IGNORECASE | re.DOTALL,
)
SYMBOL_KEY_PATTERN = re.compile(
    r'"(?:ticker|localExchangeTicker|productTicker|exchangeTicker|symbol)"\s*:\s*"(?P<symbol>[A-Z0-9._-]{2,})"',
    re.IGNORECASE,
)
ISIN_KEY_PATTERN = re.compile(
    r'"(?:isin|productIsin)"\s*:\s*"(?P<isin>[A-Z0-9]{12})"',
    re.IGNORECASE,
)
DISPLAY_NAME_KEY_PATTERN = re.compile(
    r'"(?:displayName|productName|fundName|name)"\s*:\s*"(?P<display_name>(?:\\.|[^"])*)"',
    re.IGNORECASE,
)
ASSET_CLASS_KEY_PATTERN = re.compile(
    r'"(?:assetClass|asset_class)"\s*:\s*"(?P<asset_class>(?:\\.|[^"])*)"',
    re.IGNORECASE,
)
TEXT_ISIN_PATTERN = re.compile(r"\bISIN\b\s+([A-Z]{2}[A-Z0-9]{10})\b", re.IGNORECASE)
KNOWN_ASSET_CLASSES = ("Equity", "Fixed Income", "Commodity", "Multi Asset", "Real Estate")
LOGGER = logging.getLogger(__name__)
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def normalise_catalog_candidate(candidate: dict[str, Any]) -> dict[str, str]:
    symbol = str(candidate.get("symbol", "")).strip().upper()
    isin = str(candidate.get("isin", "")).strip().upper()
    display_name = str(candidate.get("display_name", "")).strip()
    asset_class = str(candidate.get("asset_class", "")).strip() or "Unknown"
    product_url = _normalise_product_url(str(candidate.get("product_url", "")).strip())
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
        "support_status": str(candidate.get("support_status", "")).strip(),
        "support_reason_code": str(candidate.get("support_reason_code", "")).strip(),
        "support_error_detail": str(candidate.get("support_error_detail", "")).strip(),
    }


def build_catalog_report(
    discovered: int,
    catalog: list[dict[str, Any]],
    used_fallback: bool,
    extra_reason_counts: Counter[str] | None = None,
) -> dict[str, Any]:
    if extra_reason_counts is None:
        reason_counts = Counter(
            entry["support_reason_code"]
            for entry in catalog
            if entry.get("support_status") == "unsupported" and entry.get("support_reason_code")
        )
    else:
        reason_counts = Counter(extra_reason_counts)

    supported_count = sum(1 for entry in catalog if entry.get("support_status") == "supported")
    return {
        "discovered": discovered,
        "supported": supported_count,
        "unsupported": max(discovered - supported_count, 0),
        "used_fallback": used_fallback,
        "reason_counts": dict(reason_counts),
    }


def build_supported_catalog(
    candidates: list[dict[str, Any]],
    validator: Callable[[dict[str, Any]], tuple[bool, str, str]] | None = None,
    used_fallback: bool = False,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    validate = validator or _validate_candidate_support
    catalog: list[dict[str, str]] = []
    reason_counts: Counter[str] = Counter()
    seen_isins: set[str] = set()
    total_candidates = len(candidates)

    LOGGER.info("Validating support for %s ETF candidates", total_candidates)

    for index, raw_candidate in enumerate(candidates, start=1):
        candidate = normalise_catalog_candidate(raw_candidate)
        candidate_label = candidate["symbol"] or candidate["display_name"] or candidate["product_url"]
        if not candidate["isin"]:
            reason_counts["missing_isin"] += 1
            LOGGER.info(
                "Skipping candidate %s/%s (%s): missing ISIN",
                index,
                total_candidates,
                candidate_label,
            )
            continue
        if candidate["isin"] in seen_isins:
            reason_counts["duplicate_isin"] += 1
            LOGGER.info(
                "Skipping candidate %s/%s (%s): duplicate ISIN %s",
                index,
                total_candidates,
                candidate_label,
                candidate["isin"],
            )
            continue
        seen_isins.add(candidate["isin"])

        validation_started_at = perf_counter()
        is_supported, reason_code, error_detail = validate(candidate)
        validation_elapsed = _format_elapsed(perf_counter() - validation_started_at)
        candidate["support_status"] = "supported" if is_supported else "unsupported"
        candidate["support_reason_code"] = reason_code
        candidate["support_error_detail"] = error_detail
        if not is_supported:
            reason_counts[reason_code or "validation_failed"] += 1

        catalog.append(candidate)
        status_label = "supported" if is_supported else f"unsupported ({reason_code or 'validation_failed'})"
        LOGGER.info(
            "Validated candidate %s/%s (%s) in %s: %s",
            index,
            total_candidates,
            candidate_label,
            validation_elapsed,
            status_label,
        )

    catalog.sort(key=lambda entry: (entry["display_name"], entry["symbol"]))
    LOGGER.info("Finished validating ETF candidates")
    return catalog, build_catalog_report(
        discovered=len(candidates),
        catalog=catalog,
        used_fallback=used_fallback,
        extra_reason_counts=reason_counts,
    )


def write_catalog(
    catalog: list[dict[str, str]],
    output_path: Path | str = DEFAULT_ETF_CATALOG_PATH,
) -> None:
    started_at = perf_counter()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(catalog, key=lambda entry: (entry["display_name"], entry["symbol"]))
    path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
    LOGGER.info(
        "Wrote %s ETF catalog entries to %s in %s",
        len(ordered),
        path,
        _format_elapsed(perf_counter() - started_at),
    )


def get_discovery_candidate_limit() -> int | None:
    return load_app_config().catalog.discovery_candidate_limit


def discover_ishares_candidates() -> tuple[list[dict[str, str]], bool]:
    discovery_started_at = perf_counter()
    discovered: dict[str, dict[str, str]] = {}
    discovery_candidate_limit = get_discovery_candidate_limit()
    LOGGER.info("Discovering iShares ETF candidates")
    if discovery_candidate_limit is None:
        LOGGER.info("Applying unlimited discovery candidate limit")
    else:
        LOGGER.info(
            "Applying configured discovery limit: %s ETF candidates",
            discovery_candidate_limit,
        )
    for page_number in range(1, MAX_DISCOVERY_PAGES + 1):
        page_started_at = perf_counter()
        html = _fetch_discovery_html(page_number)
        LOGGER.info(
            "Fetched discovery page %s/%s in %s",
            page_number,
            MAX_DISCOVERY_PAGES,
            _format_elapsed(perf_counter() - page_started_at),
        )
        page_candidates = _extract_candidates_from_discovery_html(html)
        for candidate in page_candidates:
            discovered.setdefault(candidate["product_url"], candidate)
            if (
                discovery_candidate_limit is not None
                and len(discovered) >= discovery_candidate_limit
            ):
                break
        LOGGER.info(
            "Page %s yielded %s raw candidates; %s unique candidates so far",
            page_number,
            len(page_candidates),
            len(discovered),
        )
        if (
            discovery_candidate_limit is not None
            and len(discovered) >= discovery_candidate_limit
        ):
            LOGGER.info(
                "Reached configured discovery limit of %s ETF candidates",
                discovery_candidate_limit,
            )
            break
        if page_number > 1 and not page_candidates:
            LOGGER.info("Stopping discovery early after page %s returned no candidates", page_number)
            break

    candidates: list[dict[str, str]] = []
    unique_candidates = list(discovered.values())
    if discovery_candidate_limit is not None:
        unique_candidates = unique_candidates[:discovery_candidate_limit]
    if unique_candidates:
        LOGGER.info("Enriching %s unique ETF candidates", len(unique_candidates))
    for index, candidate in enumerate(unique_candidates, start=1):
        enrich_started_at = perf_counter()
        enriched_candidate = _enrich_candidate_identity(candidate)
        candidates.append(enriched_candidate)
        candidate_label = (
            enriched_candidate.get("symbol")
            or enriched_candidate.get("display_name")
            or enriched_candidate.get("product_url", "")
        )
        LOGGER.info(
            "Enriched candidate %s/%s (%s) in %s",
            index,
            len(unique_candidates),
            candidate_label,
            _format_elapsed(perf_counter() - enrich_started_at),
        )
    if candidates:
        LOGGER.info(
            "Discovered %s ETF candidates in %s",
            len(candidates),
            _format_elapsed(perf_counter() - discovery_started_at),
        )
        return sorted(candidates, key=lambda entry: (entry["symbol"], entry["isin"], entry["product_url"])), False

    # Fallback to the currently committed catalogue when the product-list markup changes.
    fallback_catalog = load_etf_catalog(DEFAULT_ETF_CATALOG_PATH)
    if fallback_catalog:
        LOGGER.warning(
            "Discovery returned no candidates after %s; falling back to existing catalog at %s",
            _format_elapsed(perf_counter() - discovery_started_at),
            DEFAULT_ETF_CATALOG_PATH,
        )
        return (
            [
                {
                    "symbol": entry["symbol"],
                    "isin": entry["isin"],
                    "display_name": entry["display_name"],
                    "asset_class": entry["asset_class"],
                    "product_url": entry["product_url"],
                    "holdings_url": entry["holdings_url"],
                    "support_status": entry["support_status"],
                    "support_reason_code": entry["support_reason_code"],
                    "support_error_detail": entry["support_error_detail"],
                }
                for entry in fallback_catalog
            ],
            True,
        )

    LOGGER.error(
        "Discovery returned no ETF candidates after %s and no fallback catalog was available",
        _format_elapsed(perf_counter() - discovery_started_at),
    )
    raise ValueError("No ETF candidates were discovered from the iShares product list page.")


def main() -> None:
    configure_logging()
    started_at = perf_counter()
    LOGGER.info("Starting ETF catalog generation")
    candidates, used_fallback = discover_ishares_candidates()
    catalog, report = build_supported_catalog(candidates, used_fallback=used_fallback)
    write_catalog(catalog, DEFAULT_ETF_CATALOG_PATH)
    LOGGER.info(
        "ETF catalog generation finished in %s (%s supported, %s unsupported)",
        _format_elapsed(perf_counter() - started_at),
        report["supported"],
        report["unsupported"],
    )
    print(json.dumps(report, indent=2))


def configure_logging(level: int = logging.INFO) -> None:
    if logging.getLogger().handlers:
        logging.getLogger().setLevel(level)
        return

    logging.basicConfig(level=level, format=LOG_FORMAT, stream=sys.stderr)


def _format_elapsed(seconds: float) -> str:
    return f"{seconds:.2f}s"


def _fetch_discovery_html(page_number: int) -> str:
    playwright_instance = sync_playwright().start()
    browser = playwright_instance.chromium.launch(headless=True)
    context = browser.new_context(
        locale="en-GB",
        user_agent=HEADERS_UA,
        viewport={"width": 1440, "height": 1800},
    )
    page = context.new_page()

    try:
        page.goto(
            DISCOVERY_URL_TEMPLATE.format(page_number=page_number),
            wait_until="domcontentloaded",
            timeout=60000,
        )
        accept_cookies_best_effort(page)
        page.wait_for_timeout(4500)

        return page.content()
    finally:
        close_playwright(context, browser, playwright_instance)


def _extract_candidates_from_discovery_html(html: str) -> list[dict[str, str]]:
    candidates: dict[str, dict[str, str]] = {}

    for match in DISCOVERY_TABLE_ROW_PATTERN.finditer(html):
        product_url = _normalise_product_url(
            urljoin(DISCOVERY_BASE_URL, html_lib.unescape(match.group("product_url").strip()))
        )
        symbol = html_lib.unescape(match.group("symbol")).strip().upper()
        display_name = html_lib.unescape(match.group("display_name")).strip()
        key = f"{product_url}|{symbol}|"
        candidates[key] = {
            "symbol": symbol,
            "isin": "",
            "display_name": display_name,
            "asset_class": "Unknown",
            "product_url": product_url,
            "holdings_url": "",
        }

    for match in DATA_PRODUCT_PATTERN.finditer(html):
        product_url = _normalise_product_url(
            urljoin(DISCOVERY_BASE_URL, html_lib.unescape(match.group("product_url").strip()))
        )
        symbol = match.group("symbol").strip().upper()
        isin = match.group("isin").strip().upper()
        key = f"{product_url}|{symbol}|{isin}"
        candidates[key] = {
            "symbol": symbol,
            "isin": isin,
            "display_name": symbol,
            "asset_class": "Unknown",
            "product_url": product_url,
            "holdings_url": "",
        }

    for match in DISCOVERY_TEXT_LINK_PATTERN.finditer(html):
        product_url = _normalise_product_url(
            urljoin(DISCOVERY_BASE_URL, html_lib.unescape(match.group("product_url").strip()))
        )
        symbol = match.group("symbol").strip().upper()
        context_window = html[max(0, match.start() - 800) : match.end() + 200]
        display_name = _extract_display_name(context_window) or symbol
        asset_class = _extract_asset_class(context_window) or "Unknown"
        key = f"{product_url}|{symbol}|"
        candidates.setdefault(
            key,
            {
                "symbol": symbol,
                "isin": "",
                "display_name": display_name,
                "asset_class": asset_class,
                "product_url": product_url,
                "holdings_url": "",
            },
        )

    for product_match in PRODUCT_URL_PATTERN.finditer(html):
        product_url = urljoin(
            DISCOVERY_BASE_URL,
            html_lib.unescape(product_match.group("product_url").strip()).replace("\\/", "/"),
        )
        product_url = _normalise_product_url(product_url)
        window = html[max(0, product_match.start() - 1500) : min(len(html), product_match.end() + 1500)]
        symbol_match = SYMBOL_KEY_PATTERN.search(window)
        isin_match = ISIN_KEY_PATTERN.search(window)
        symbol = "" if symbol_match is None else symbol_match.group("symbol").strip().upper()
        isin = "" if isin_match is None else isin_match.group("isin").strip().upper()
        display_name = _extract_display_name(window) or symbol
        asset_class = _extract_asset_class(window) or "Unknown"
        if not symbol and not isin:
            continue
        key = f"{product_url}|{symbol}|{isin}"
        candidates.setdefault(
            key,
            {
                "symbol": symbol,
                "isin": isin,
                "display_name": display_name or symbol,
                "asset_class": asset_class,
                "product_url": product_url,
                "holdings_url": "",
            },
        )

    return list(candidates.values())


def _enrich_candidate_identity(candidate: dict[str, str]) -> dict[str, str]:
    if candidate.get("isin") and candidate.get("asset_class", "").strip() not in {"", "Unknown"}:
        return candidate

    candidate["product_url"] = _normalise_product_url(candidate["product_url"])
    html, _, context, browser, playwright_instance = fetch_rendered_html_and_request_ctx(
        candidate["product_url"]
    )
    try:
        page_text = _html_to_text(html)
        if not candidate.get("display_name"):
            candidate["display_name"] = _extract_display_name(html) or candidate.get("display_name", "")
        if not candidate.get("isin"):
            isin_match = TEXT_ISIN_PATTERN.search(page_text)
            if isin_match:
                candidate["isin"] = isin_match.group(1).strip().upper()
        if candidate.get("asset_class", "").strip() in {"", "Unknown"}:
            candidate["asset_class"] = _extract_asset_class(page_text) or "Unknown"
    finally:
        close_playwright(context, browser, playwright_instance)

    return candidate


def _html_to_text(html: str) -> str:
    plain_text = re.sub(r"<[^>]+>", " ", html_lib.unescape(html))
    return re.sub(r"\s+", " ", plain_text).strip()


def _normalise_product_url(product_url: str) -> str:
    cleaned = str(product_url).strip()
    if not cleaned:
        return ""

    parsed = urlsplit(cleaned)
    if "ishares.com" not in parsed.netloc.casefold() or not parsed.path.startswith("/uk/individual/en/products/"):
        return cleaned

    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params.setdefault("siteEntryPassthrough", "true")
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query_params),
            parsed.fragment,
        )
    )


def _extract_display_name(text: str) -> str:
    key_match = DISPLAY_NAME_KEY_PATTERN.search(text)
    if key_match:
        return html_lib.unescape(key_match.group("display_name")).replace('\\"', '"').strip()

    name_matches = re.findall(r"(iShares[^<\n]{5,200})", html_lib.unescape(text), re.IGNORECASE)
    return "" if not name_matches else re.sub(r"\s+", " ", name_matches[-1]).strip()


def _extract_asset_class(text: str) -> str:
    key_match = ASSET_CLASS_KEY_PATTERN.search(text)
    if key_match:
        asset_class = html_lib.unescape(key_match.group("asset_class")).replace('\\"', '"').strip()
        return re.sub(r"\s+", " ", asset_class)

    for asset_class in KNOWN_ASSET_CLASSES:
        if asset_class.casefold() in text.casefold():
            return asset_class
    return ""


def _validate_candidate_support(candidate: dict[str, Any]) -> tuple[bool, str, str]:
    try:
        holdings, validation, holdings_url = fetch_standardised_holdings_snapshot(
            symbol=candidate["symbol"],
            isin=candidate["isin"],
            product_page=candidate["product_url"],
        )
    except ValueError as exc:
        message = str(exc)
        if "No CSV ajax links found" in message:
            return False, "no_holdings_url", message
        if "Unable to parse holdings CSV" in message:
            return False, "parse_failed", message
        if "CSV download failed" in message:
            return False, "fetch_failed", message
        return False, "fetch_failed", message
    except Exception as exc:  # pragma: no cover - network/runtime fallback
        return False, "fetch_failed", str(exc)

    if holdings.empty:
        return False, "validation_failed", "Standardised holdings were empty."
    if not validation.positive_weight_sum_in_expected_band:
        return False, "validation_failed", "Standardised holdings failed validation checks."

    candidate["holdings_url"] = holdings_url
    return True, "", ""


if __name__ == "__main__":
    main()
