# Vanguard VWRP and VAGS Support Design

## Goal

Extend the portfolio analysis tool so it can refresh and analyze the Vanguard UK/UCITS ETFs VWRP and VAGS alongside the existing iShares ETF catalogue.

The initial Vanguard scope is deliberately limited to:

- VWRP: Vanguard FTSE All-World UCITS ETF, GBP London Stock Exchange ticker, ISIN IE00BK5BQT80.
- VAGS: Vanguard Global Aggregate Bond UCITS ETF GBP Hedged Accumulating, ISIN IE00BG47K971.

This is not a full Vanguard catalogue discovery project.

## Current Context

The app already has two useful foundations:

- The committed ETF catalogue is issuer-aware through `issuer_key`, `product_url`, `holdings_url`, and support metadata.
- The portfolio builder, saved portfolio resolution, snapshot refresh, and report builder mostly consume normalized holdings rather than iShares-specific raw data.

The main iShares assumptions are concentrated in `data_retrival.py` and `generate_etf_catalog.py`:

- iShares product pages are rendered with Playwright.
- A BlackRock/iShares `.ajax?fileType=csv` holdings URL is extracted from rendered HTML.
- The resulting CSV is parsed into the standard holdings schema.
- Catalogue generation discovers and validates only iShares candidates.

Vanguard support should therefore be added at the retrieval/provider boundary, not by forcing Vanguard pages through iShares URL extraction.

## Vanguard Source Shape

Official Vanguard UK pages expose the required product identity and holdings concepts:

- VWRP product page: `https://www.vanguard.co.uk/professional/product/etf/equity/9679/ftse-all-world-ucits-etf-accumulating`
- VAGS product page: `https://www.vanguard.co.uk/uk-fund-directory/product/etf/bond/9685/global-aggregate-bond-ucits`

VWRP holdings include holding name, percent of market value, sector, region, market value, and shares.

VAGS holdings include holding name, percent of market value, market value, face amount, coupon/yield, and maturity date. Its page also exposes fund-level country/region allocation and bond distribution tables, but individual bond rows may not have a company-country-sector shape equivalent to equity holdings.

## Architecture

Add a small provider layer in retrieval code:

- `ishares` keeps the current rendered-page CSV resolver and parser behavior.
- `vanguard` gets a Vanguard-specific resolver/parser.
- public refresh paths choose the provider from catalogue metadata or product URL instead of assuming iShares.

The normalized output remains:

```text
company, country, sector, asset_class, weight_pct, holding_type, is_cash_equivalent
```

The rest of the app should continue reading cached parquet snapshots and should not need to know whether the source was iShares or Vanguard.

## Catalogue Entries

Add two supported entries to `src/portfolio_analysis_app/data/etf_catalog.json`:

- `vanguard-vwrp-ie00bk5bqt80`
- `vanguard-vags-ie00bg47k971`

Each entry should include:

- `issuer_key`: `vanguard`
- `symbol`: `VWRP` or `VAGS`
- `isin`
- `display_name`
- `asset_class`: `Equity` for VWRP and `Fixed Income` for VAGS
- `product_url`: official Vanguard product page
- `holdings_url`: resolved Vanguard holdings download URL if available, otherwise the product page URL when the provider parser extracts from rendered page content
- support metadata marked supported only after the retrieval parser validates a non-empty holdings snapshot with a plausible positive weight sum

## Vanguard Holdings Handling

For VWRP:

- Map `Holding name` to `company`.
- Map `% of market value` to `weight_pct`.
- Map `Sector` to `sector`.
- Map `Region` to `country` if no more precise per-holding country exists in the downloadable data.
- Set `asset_class` to `Equity`.

For VAGS:

- Map `Holding name` to `company`.
- Map `% of market value` to `weight_pct`.
- Set `asset_class` to `Fixed Income`.
- Set `sector` to a stable fixed-income label, preferably `Fixed Income`, unless the downloadable data provides a more specific issuer/credit category.
- Set `country` to `Unknown` when the row-level data does not provide it. Do not infer country from bond names unless a dedicated, reliable field exists.

The report builder already tolerates unknown country and sector labels, so missing per-bond geography is acceptable for the first version.

## Error Handling

Vanguard parsing failures should use the existing support reason model:

- `no_holdings_url` when no downloadable or parseable holdings source can be found.
- `parse_failed` when a source is found but cannot be mapped to the normalized holdings schema.
- `fetch_failed` for request, browser, timeout, or HTTP failures.
- `validation_failed` for empty snapshots or implausible weight totals.

Validation should stay provider-neutral: non-empty holdings plus a positive weight sum in the existing expected band unless Vanguard bond rows require a narrow documented exception discovered during implementation.

## Tests

Add focused tests for:

- Provider selection routes iShares entries to the existing resolver and Vanguard entries to the Vanguard resolver.
- Catalogue entries for VWRP and VAGS validate with required fields and stable ETF IDs.
- Vanguard equity holdings parsing maps name, weight, sector, and region into the standard schema.
- Vanguard bond holdings parsing preserves bond rows and assigns stable fixed-income metadata without inventing missing country values.
- Snapshot refresh works for a resolved Vanguard entry through mocked provider functions.

Avoid live network tests in unit tests. Keep official Vanguard URL validation as manual/runtime behavior.

## Out of Scope

- Discovering the full Vanguard UK ETF universe.
- Supporting US Vanguard ETFs.
- Reworking dashboard UX for fixed income analytics.
- Adding bond-specific duration, maturity, coupon, or credit-quality analytics.
- Replacing iShares catalogue generation.

## Implementation Notes

Because the working tree currently contains broad local modifications, implementation should make narrowly scoped edits and avoid unrelated formatting churn. The provider layer should be small enough that future Vanguard catalogue discovery can plug into it later, but it should not require that discovery work now.
