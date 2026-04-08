# Single ETF Analysis Design

## Goal

Add a dedicated `Single ETF Analysis` area to the Streamlit dashboard so the user can inspect each ETF individually across companies, countries, and sectors.

## Scope

This change extends the dashboard and report layer only.

- Keep the existing PIE dashboard intact.
- Add a new top-level tab for single-ETF analysis.
- Use the existing `combined_holdings` dataset as the source of truth.

## User Experience

The dashboard will gain a new top-level tab named `Single ETF Analysis`.

Inside this tab:

- the user selects one ETF from `SWDA`, `EMIM`, or `WSML`
- the page shows three stacked sections:
  - companies
  - countries
  - sectors

Each section should use the same visual language as the current dashboard:

- bar chart for the top items
- companion table for the same data

The values shown in this area should be ETF-internal weights, not PIE portfolio contribution percentages. When the user analyzes a single ETF, the most useful question is "what is inside this ETF?"

## Architecture

### Report Layer

Add helper logic in `portfolio_analysis.py` that filters `combined_holdings` by `parent_etf` and computes exposures for:

- company
- country
- sector

The calculations should aggregate from `weight_pct`, because the single-ETF view is meant to reflect the ETF's own composition. The report should also expose the list of available ETFs so the UI can populate the selector without hardcoding assumptions in the page layer.

### Streamlit Layer

Add one top-level tab to `app.py` for `Single ETF Analysis`.

Inside that tab:

- render an ETF selector
- show three stacked analysis blocks
- reuse the existing chart and table helpers where possible

This keeps the UI consistent with the current dashboard and avoids creating an entirely separate page structure.

## Data Flow

1. `build_report(...)` loads `combined_holdings`.
2. The report exposes available ETF identifiers and the data needed to derive ETF-specific exposures.
3. `app.py` reads the selected ETF value from the new tab control.
4. The app renders company, country, and sector views for that ETF only.

## Edge Cases

- If an ETF has no rows for a snapshot, show a friendly info message instead of empty charts.
- If some labels are missing, continue to use the existing `Unknown` handling.
- If Plotly is unavailable, keep the existing bar-chart fallback behavior.

## Testing

Add report-layer tests to verify:

- ETF filtering returns only rows for the selected ETF
- company, country, and sector exposures use `weight_pct`
- ETF-level exposures sum to approximately `100%`

After implementation, smoke-test one known ETF such as `SWDA` to confirm:

- the new tab renders
- the three sections appear in order
- the exposure totals reflect ETF-internal composition rather than PIE contribution

## Out of Scope

- replacing the main PIE overview with single-ETF mode
- drilldowns inside the single-ETF tab
- new data files or changes to `data_retrival.py`
