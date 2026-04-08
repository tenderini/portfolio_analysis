# ETF Composition Pie Design

## Goal

Add a fixed portfolio-composition pie chart to the Streamlit dashboard so the user can immediately see how the PIE portfolio is split across its three component ETFs: `SWDA`, `EMIM`, and `WSML`.

## Scope

This change is limited to the dashboard and report-building layer.

- Keep `data_retrival.py` unchanged.
- Add a compact ETF-composition dataset to the report returned by `build_report(...)`.
- Render a new `Portfolio Composition` section at the top of the `Overview` tab.

## User Experience

The new section will appear above the existing `Top Exposures` section in the `Overview` tab.

- Left column: a 3-slice pie chart showing ETF allocation by portfolio weight.
- Right column: a compact companion table showing ETF ticker and allocation percentage.

The chart is fixed for the selected snapshot and does not react to company, country, or sector drilldowns. This keeps it focused on the portfolio's structural allocation and avoids duplicating the existing ETF drilldown tables elsewhere in the app.

## Architecture

### Report Layer

Add a small ETF-composition builder in `portfolio_analysis.py` that derives portfolio allocation from `combined_holdings`.

- Group by `parent_etf`.
- Collapse `pie_weight` to a single value per ETF.
- Convert the weight into percentage points for display consistency with the rest of the app.
- Return the result as a sorted dataframe, for example under `report["etf_composition"]`.

This keeps the allocation logic centralized in the report builder instead of hardcoding static values in the Streamlit UI.

### Streamlit Layer

Add a reusable `render_pie_chart(...)` helper in `app.py`, adjacent to the current chart helpers.

The `Overview` tab will gain a `Portfolio Composition` block rendered in two columns:

- pie chart column
- table column

Both visual elements will consume the same `report["etf_composition"]` dataframe so the displayed values stay aligned.

## Data Flow

1. `load_report(snapshot_date)` calls `build_report(...)`.
2. `build_report(...)` loads `combined_holdings` and computes `etf_composition`.
3. `app.py` reads `report["etf_composition"]` when rendering the `Overview` tab.
4. The pie chart and companion table are both generated from that shared dataframe.

## Edge Cases

- If one ETF is missing from a snapshot, render the remaining available slices instead of failing.
- If the composition dataframe is empty, show a friendly info message rather than an empty chart.
- If Plotly is unavailable, skip the pie chart and still render the table so the section remains useful.

## Testing

Add a focused test around the ETF-composition builder to verify:

- one row is produced per ETF
- the resulting allocation totals approximately `100%`
- the output is sorted in descending allocation order

After implementation, smoke-test the Streamlit app to confirm:

- the new section appears above `Top Exposures`
- the pie and table show the same numbers
- the layout remains readable in the existing wide dashboard layout

## Out of Scope

- changing the ETF weights in `data_retrival.py`
- adding a separate composition tab
- making the ETF composition chart react to drilldown selections

## Review Notes

The visual-companion browser helper could not be used in this environment because `node` is not installed in the shell, so the design was validated through text discussion instead.
