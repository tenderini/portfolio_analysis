"""
data_retrival.py

Fetch iShares ETF holdings + compute exposures (company / country / sector)
for a 3-ETF Pie (SWDA, EMIM, WSML/WLDS) using Playwright to bypass
JS/consent gating and 403s on the CSV endpoint.

How to run (macOS):
  source .venv/bin/activate
  pip install pandas pyarrow playwright
  playwright install chromium
  python data_retrival.py

Outputs (./data):
  - <SYMBOL>_raw_holdings_<YYYYMMDD>.csv
  - <SYMBOL>_holdings_<YYYYMMDD>.parquet / .csv
  - <SYMBOL>_country_<YYYYMMDD>.csv
  - <SYMBOL>_sector_<YYYYMMDD>.csv
  - <SYMBOL>_top_companies_<YYYYMMDD>.csv
  - PIE_company_exposure_<YYYYMMDD>.csv
  - PIE_country_exposure_<YYYYMMDD>.csv
  - PIE_sector_exposure_<YYYYMMDD>.csv
  - validation_report_<YYYYMMDD>.json
  - run_metadata_<YYYYMMDD>.json
"""

from __future__ import annotations

import io
import json
import os
import re
import html as html_lib
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# -----------------------
# Configuration
# -----------------------

HEADERS_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = str(REPO_ROOT / "data")
os.makedirs(DATA_DIR, exist_ok=True)

TODAY = datetime.utcnow().strftime("%Y%m%d")


@dataclass(frozen=True)
class ETF:
    symbol: str
    isin: str
    product_page: str   # BlackRock product page (more stable than ishares.com)
    pie_weight: float


@dataclass(frozen=True)
class HoldingsValidation:
    raw_rows: int
    raw_columns: list[str]
    resolved_weight_column: str
    rows_with_numeric_weight: int
    rows_with_positive_weight: int
    rows_with_non_positive_weight: int
    standardised_rows: int
    dropped_rows_vs_raw: int
    dropped_rows_vs_positive_weight: int
    missing_company_rows: int
    missing_country_rows: int
    missing_sector_rows: int
    raw_numeric_weight_sum: float
    positive_weight_sum: float
    standardised_weight_sum: float
    weight_sum_delta_vs_positive_rows: float
    positive_weight_sum_in_expected_band: bool


ETF_CONFIG = [
    ETF(
        symbol="SWDA",
        isin="IE00B4L5Y983",
        product_page="https://www.blackrock.com/uk/individual/products/251882/ishares-msci-world-ucits-etf-acc-fund",
        pie_weight=0.78,
    ),
    ETF(
        symbol="EMIM",
        isin="IE00BKM4GZ66",
        product_page="https://www.blackrock.com/uk/individual/products/264659/ishares-msci-emerging-markets-imi-ucits-etf",
        pie_weight=0.12,
    ),
    ETF(
        symbol="WSML",  # sometimes seen as WLDS/WSML on brokers; ISIN is the key
        isin="IE00BF4RFH31",
        product_page="https://www.blackrock.com/uk/individual/products/296576/ishares-msci-world-small-cap-ucits-etf",
        pie_weight=0.10,
    ),
]


# -----------------------
# Playwright helpers
# -----------------------

def accept_cookies_best_effort(page) -> None:
    """
    Best-effort click on common cookie/consent accept buttons.
    Harmless if not present.
    """
    selectors = [
        "button#onetrust-accept-btn-handler",
        "button:has-text('Accept all')",
        "button:has-text('Accept All')",
        "button:has-text('Accept')",
        "button:has-text('I Accept')",
        "button:has-text('Agree')",
        "button:has-text('OK')",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                loc.click(timeout=1500)
                return
        except Exception:
            continue


def fetch_rendered_html_and_request_ctx(url: str) -> Tuple[str, object, object, object, object]:
    """
    Opens a headless Chromium page, handles consent best-effort,
    returns (html, request_context, context, browser, playwright_instance).

    We return the objects so the caller can close them in a finally block.
    """
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        locale="en-GB",
        user_agent=HEADERS_UA,
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        accept_cookies_best_effort(page)
        page.wait_for_timeout(2000)  # let JS settle
        html = page.content()
        return html, context.request, context, browser, p
    except PlaywrightTimeoutError:
        # Save what we can for debugging
        try:
            html = page.content()
        except Exception:
            html = ""
        with open(os.path.join(DATA_DIR, "debug_timeout_page.html"), "w", encoding="utf-8") as f:
            f.write(html)
        context.close()
        browser.close()
        p.stop()
        raise


def close_playwright(context, browser, p) -> None:
    try:
        context.close()
    except Exception:
        pass
    try:
        browser.close()
    except Exception:
        pass
    try:
        p.stop()
    except Exception:
        pass


# -----------------------
# iShares/BlackRock CSV resolver + downloader
# -----------------------

def extract_holdings_csv_url(product_page_url: str, rendered_html: str) -> str:
    """
    Extract an ajax CSV URL from the rendered HTML.

    BlackRock/iShares often embed something like:
      /.../1472631233320.ajax?fileType=csv&fileName=...&dataType=fund

    NOTE: sometimes HTML has &amp; entities -> unescape().
    """
    # Prefer links containing holdings in fileName if possible
    candidates = []

    # 1) Relative ajax links
    for m in re.finditer(r'(/[^"\']+\.ajax\?[^"\']*fileType=csv[^"\']*)', rendered_html, re.IGNORECASE):
        candidates.append(m.group(1))

    # 2) Absolute ajax links
    for m in re.finditer(r'(https?://[^"\']+\.ajax\?[^"\']*fileType=csv[^"\']*)', rendered_html, re.IGNORECASE):
        candidates.append(m.group(1))

    if not candidates:
        # Save rendered HTML for inspection
        dbg_path = os.path.join(DATA_DIR, "debug_no_csv_link.html")
        with open(dbg_path, "w", encoding="utf-8") as f:
            f.write(rendered_html)
        raise ValueError(
            f"No CSV ajax links found on page: {product_page_url}. "
            f"Saved HTML to {dbg_path} (search for 'fileType=csv')."
        )

    # Unescape entities (&amp;)
    candidates = [html_lib.unescape(c) for c in candidates]

    # Make absolute if needed
    abs_candidates = []
    for c in candidates:
        if c.startswith("http"):
            abs_candidates.append(c)
        else:
            abs_candidates.append(product_page_url.rstrip("/") + c if c.startswith("/") else product_page_url.rstrip("/") + "/" + c)

    # Rank candidates: prefer those whose query includes holdings
    def score(u: str) -> int:
        u_low = u.lower()
        s = 0
        if "hold" in u_low or "holding" in u_low or "holdings" in u_low:
            s += 10
        if "datatype=fund" in u_low:
            s += 3
        if "filename=" in u_low:
            s += 1
        return s

    abs_candidates.sort(key=score, reverse=True)
    return abs_candidates[0]


def download_csv_via_playwright(request_ctx, csv_url: str, referer: str) -> str:
    """
    Download CSV using the Playwright request context so cookies/session are preserved.
    Add Referer to reduce hotlink blocks.
    """
    resp = request_ctx.get(
        csv_url,
        headers={
            "Referer": referer,
            "User-Agent": HEADERS_UA,
            "Accept": "text/csv,*/*;q=0.9",
        },
        timeout=60000,
    )
    if not resp.ok:
        raise ValueError(f"CSV download failed: HTTP {resp.status} {resp.status_text} for {csv_url}")
    return resp.text()


# -----------------------
# CSV parsing + standardisation
# -----------------------

def parse_holdings_csv(csv_text: str) -> pd.DataFrame:
    """
    iShares holdings CSV often includes a metadata header.
    We attempt skiprows until we find a 'Weight' column.
    """
    last_err: Optional[Exception] = None
    for skip in range(0, 25):
        try:
            df = pd.read_csv(io.StringIO(csv_text), skiprows=skip)
            cols_lower = [str(c).strip().lower() for c in df.columns]
            if any(c.startswith("weight") for c in cols_lower):
                return df
        except Exception as e:
            last_err = e
            continue
    raise ValueError(f"Unable to parse holdings CSV. Last error: {last_err}")


def _pick_matching_column(columns: list[str], possible: list[str]) -> Optional[str]:
    for p in possible:
        for c in columns:
            if c.strip().lower() == p.strip().lower():
                return c
    return None


def _extract_standard_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    weight_col = None
    for c in df.columns:
        if c.strip().lower().startswith("weight"):
            weight_col = c
            break
    if weight_col is None:
        raise ValueError("No weight column found in CSV.")

    name_col = _pick_matching_column(df.columns.tolist(), ["Name", "Security Name", "Issuer Name", "Holding Name"])
    country_col = _pick_matching_column(df.columns.tolist(), ["Location", "Country", "Country of Risk", "Market"])
    sector_col = _pick_matching_column(df.columns.tolist(), ["Sector", "GICS Sector", "Industry Sector"])
    asset_class_col = _pick_matching_column(df.columns.tolist(), ["Asset Class"])

    out = pd.DataFrame({
        "company": df[name_col] if name_col else pd.Series(index=df.index, dtype="object"),
        "country": df[country_col] if country_col else pd.Series(index=df.index, dtype="object"),
        "sector": df[sector_col] if sector_col else pd.Series(index=df.index, dtype="object"),
        "asset_class": df[asset_class_col] if asset_class_col else pd.Series(index=df.index, dtype="object"),
        "weight_pct": pd.to_numeric(df[weight_col], errors="coerce"),
    })
    return out, weight_col


def classify_holding_types(holdings: pd.DataFrame) -> pd.DataFrame:
    classified = holdings.copy()
    sector = classified["sector"].fillna("").astype(str).str.strip().str.casefold()
    asset_class = classified["asset_class"].fillna("").astype(str).str.strip().str.casefold()
    is_cash_equivalent = (
        sector.eq("cash and/or derivatives")
        | asset_class.str.contains("cash", regex=False)
        | asset_class.str.contains("derivative", regex=False)
    )
    classified["is_cash_equivalent"] = is_cash_equivalent
    classified["holding_type"] = "security"
    classified.loc[is_cash_equivalent, "holding_type"] = "cash_derivative"
    return classified


def standardise_holdings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Output columns:
      company, country, sector, asset_class, weight_pct, holding_type, is_cash_equivalent
    """
    out, _ = _extract_standard_columns(df)
    out = out.dropna(subset=["weight_pct"])
    out = out[out["weight_pct"] > 0]
    return classify_holding_types(out)


def validate_holdings_capture(raw_df: pd.DataFrame, holdings: pd.DataFrame) -> HoldingsValidation:
    extracted, weight_col = _extract_standard_columns(raw_df)
    text_cols = ["company", "country", "sector"]

    for col in text_cols:
        extracted[col] = extracted[col].fillna("").astype(str).str.strip()

    numeric_weight = extracted["weight_pct"].notna()
    positive_weight = extracted["weight_pct"] > 0

    raw_numeric_weight_sum = float(extracted.loc[numeric_weight, "weight_pct"].sum())
    positive_weight_sum = float(extracted.loc[positive_weight, "weight_pct"].sum())
    standardised_weight_sum = float(holdings["weight_pct"].sum())

    return HoldingsValidation(
        raw_rows=int(len(raw_df)),
        raw_columns=raw_df.columns.astype(str).tolist(),
        resolved_weight_column=weight_col,
        rows_with_numeric_weight=int(numeric_weight.sum()),
        rows_with_positive_weight=int(positive_weight.sum()),
        rows_with_non_positive_weight=int((numeric_weight & ~positive_weight).sum()),
        standardised_rows=int(len(holdings)),
        dropped_rows_vs_raw=int(len(raw_df) - len(holdings)),
        dropped_rows_vs_positive_weight=int(positive_weight.sum() - len(holdings)),
        missing_company_rows=int((extracted["company"] == "").sum()),
        missing_country_rows=int((extracted["country"] == "").sum()),
        missing_sector_rows=int((extracted["sector"] == "").sum()),
        raw_numeric_weight_sum=round(raw_numeric_weight_sum, 6),
        positive_weight_sum=round(positive_weight_sum, 6),
        standardised_weight_sum=round(standardised_weight_sum, 6),
        weight_sum_delta_vs_positive_rows=round(standardised_weight_sum - positive_weight_sum, 6),
        positive_weight_sum_in_expected_band=95.0 <= positive_weight_sum <= 105.0,
    )


# -----------------------
# Analytics + persistence
# -----------------------

def fetch_standardised_holdings_snapshot(
    symbol: str,
    isin: str,
    product_page: str,
    pie_weight: float = 0.0,
) -> Tuple[pd.DataFrame, HoldingsValidation, str]:
    etf = ETF(symbol=symbol, isin=isin, product_page=product_page, pie_weight=pie_weight)
    html, request_context, context, browser, playwright_instance = fetch_rendered_html_and_request_ctx(
        etf.product_page
    )
    try:
        csv_url = extract_holdings_csv_url(etf.product_page, html)
        csv_text = download_csv_via_playwright(
            request_context,
            csv_url,
            referer=etf.product_page,
        )
        raw_df = parse_holdings_csv(csv_text)
        holdings = standardise_holdings(raw_df)
        validation = validate_holdings_capture(raw_df, holdings)
        return holdings, validation, csv_url
    finally:
        close_playwright(context, browser, playwright_instance)


def save_raw_csv_output(etf: ETF, csv_text: str) -> str:
    raw_path = os.path.join(DATA_DIR, f"{etf.symbol}_{TODAY}_raw_holdings.csv")
    with open(raw_path, "w", encoding="utf-8", newline="") as f:
        f.write(csv_text)
    return raw_path


def save_etf_outputs(etf: ETF, holdings: pd.DataFrame, meta: Dict[str, Any], validation: HoldingsValidation, raw_csv_path: str) -> None:
    """
    Save holdings + breakdowns for one ETF.
    """
    base = os.path.join(DATA_DIR, f"{etf.symbol}_{TODAY}")

    holdings.to_parquet(f"{base}_holdings.parquet", index=False)
    holdings.to_csv(f"{base}_holdings.csv", index=False)

    # Aggregations
    top_companies = holdings.groupby("company", dropna=True)["weight_pct"].sum().sort_values(ascending=False).head(50)
    countries = holdings.groupby("country", dropna=True)["weight_pct"].sum().sort_values(ascending=False)
    sectors = holdings.groupby("sector", dropna=True)["weight_pct"].sum().sort_values(ascending=False)

    top_companies.to_csv(f"{base}_top_companies.csv")
    countries.to_csv(f"{base}_country.csv")
    sectors.to_csv(f"{base}_sector.csv")

    existing_meta = meta["etfs"].get(etf.symbol, {})
    meta["etfs"][etf.symbol] = {
        **existing_meta,
        "isin": etf.isin,
        "product_page": etf.product_page,
        "pie_weight": etf.pie_weight,
        "holdings_rows": int(len(holdings)),
        "files_prefix": f"{etf.symbol}_{TODAY}",
        "raw_csv_path": raw_csv_path,
        "validation": asdict(validation),
    }


def compute_pie_exposures(standardised_holdings_by_etf: Dict[str, pd.DataFrame]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Combine ETF holdings into Pie exposures using each ETF's pie_weight.

    Returns:
      companies_df: company, contribution_pct
      countries_df: country, contribution_pct
      sectors_df: sector, contribution_pct
    """
    combined_rows = []
    for etf in ETF_CONFIG:
        df = standardised_holdings_by_etf[etf.symbol].copy()
        df["pie_weight"] = etf.pie_weight
        df["contribution_pct"] = df["weight_pct"] * etf.pie_weight
        df["parent_etf"] = etf.symbol
        combined_rows.append(df)

    combined = pd.concat(combined_rows, ignore_index=True)

    companies = (
        combined.groupby("company", dropna=True)["contribution_pct"]
        .sum().sort_values(ascending=False).reset_index()
    )
    countries = (
        combined.groupby("country", dropna=True)["contribution_pct"]
        .sum().sort_values(ascending=False).reset_index()
    )
    sectors = (
        combined.groupby("sector", dropna=True)["contribution_pct"]
        .sum().sort_values(ascending=False).reset_index()
    )

    # Save the combined detail too (optional)
    combined.to_parquet(os.path.join(DATA_DIR, f"PIE_combined_holdings_detail_{TODAY}.parquet"), index=False)

    return companies, countries, sectors


def main() -> None:
    run_meta = {
        "run_utc": datetime.utcnow().isoformat(),
        "data_dir": DATA_DIR,
        "etfs": {},
        "validation_summary": {},
        "notes": [
            "Holdings are fetched via Playwright to preserve cookies/session and avoid 403 on CSV endpoint.",
            "All outputs are snapshots with date suffix YYYYMMDD; refresh frequency can be monthly/weekly as desired.",
            "Validation metadata compares parsed raw rows with the standardised holdings snapshot to surface dropped rows and weight-total anomalies.",
        ],
    }

    holdings_by_etf: Dict[str, pd.DataFrame] = {}

    for etf in ETF_CONFIG:
        print(f"\n=== {etf.symbol} ({etf.isin}) ===")
        html, req_ctx, context, browser, p = fetch_rendered_html_and_request_ctx(etf.product_page)
        try:
            csv_url = extract_holdings_csv_url(etf.product_page, html)
            csv_text = download_csv_via_playwright(req_ctx, csv_url, referer=etf.product_page)
            raw_csv_path = save_raw_csv_output(etf, csv_text)

            raw_df = parse_holdings_csv(csv_text)
            holdings = standardise_holdings(raw_df)
            validation = validate_holdings_capture(raw_df, holdings)

            print(f"Holdings rows: {len(holdings)}")
            print(
                "Validation:"
                f" raw_rows={validation.raw_rows},"
                f" positive_weight_rows={validation.rows_with_positive_weight},"
                f" standardised_rows={validation.standardised_rows},"
                f" positive_weight_sum={validation.positive_weight_sum:.4f},"
                f" standardised_weight_sum={validation.standardised_weight_sum:.4f}"
            )
            print("Top 5 holdings:")
            print(holdings.sort_values("weight_pct", ascending=False).head(5)[["company", "weight_pct"]].to_string(index=False))

            holdings_by_etf[etf.symbol] = holdings

            # Save + meta
            run_meta["etfs"][etf.symbol] = {
                "isin": etf.isin,
                "product_page": etf.product_page,
                "pie_weight": etf.pie_weight,
                "csv_url": csv_url,
                "rows": int(len(holdings)),
                "raw_csv_path": raw_csv_path,
                "validation": asdict(validation),
            }
            run_meta["validation_summary"][etf.symbol] = asdict(validation)

            # Persist ETF outputs
            save_etf_outputs(etf, holdings, run_meta, validation, raw_csv_path)

        finally:
            close_playwright(context, browser, p)

    # Compute Pie exposures
    companies, countries, sectors = compute_pie_exposures(holdings_by_etf)

    # Save Pie results
    companies.to_csv(os.path.join(DATA_DIR, f"PIE_company_exposure_{TODAY}.csv"), index=False)
    countries.to_csv(os.path.join(DATA_DIR, f"PIE_country_exposure_{TODAY}.csv"), index=False)
    sectors.to_csv(os.path.join(DATA_DIR, f"PIE_sector_exposure_{TODAY}.csv"), index=False)

    print("\n=== PIE EXPOSURES (Top 15) ===")
    print("\nTop Companies:")
    print(companies.head(15).to_string(index=False))
    print("\nTop Countries:")
    print(countries.head(15).to_string(index=False))
    print("\nTop Sectors:")
    print(sectors.head(15).to_string(index=False))

    # Save run metadata
    meta_path = os.path.join(DATA_DIR, f"run_metadata_{TODAY}.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(run_meta, f, indent=2)

    validation_path = os.path.join(DATA_DIR, f"validation_report_{TODAY}.json")
    with open(validation_path, "w", encoding="utf-8") as f:
        json.dump(run_meta["validation_summary"], f, indent=2)

    print(f"\nSaved all outputs in ./{DATA_DIR}/")
    print(f"Run metadata: {meta_path}")
    print(f"Validation report: {validation_path}")


if __name__ == "__main__":
    main()
