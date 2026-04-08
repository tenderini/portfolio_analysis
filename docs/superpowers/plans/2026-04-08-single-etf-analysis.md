# Single ETF Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `Single ETF Analysis` tab that lets the user choose `SWDA`, `EMIM`, or `WSML` and inspect company, country, and sector exposures for that ETF alone.

**Architecture:** Extend `portfolio_analysis.py` with ETF-specific exposure helpers built from `combined_holdings` filtered by `parent_etf`, using `weight_pct` as the aggregation basis. Then render a new top-level Streamlit tab in `app.py` with an ETF selector and three stacked sections reusing the current chart and table helpers.

**Tech Stack:** Python, pandas, Streamlit, optional Plotly, unittest

---

### Task 1: Add the report-layer failing tests

**Files:**
- Modify: `tests/test_portfolio_analysis.py`
- Test: `tests/test_portfolio_analysis.py`

- [ ] **Step 1: Write the failing tests**

```python
from portfolio_analysis import _build_single_etf_dimension_exposure, build_report


    def test_build_single_etf_dimension_exposure_uses_weight_pct_for_selected_etf(self) -> None:
        combined_holdings = pd.DataFrame(
            {
                "parent_etf": ["SWDA", "SWDA", "EMIM", "SWDA"],
                "company": ["Apple", "Microsoft", "Tencent", "Apple"],
                "country": ["US", "US", "CN", "US"],
                "sector": ["Tech", "Tech", "Tech", "Tech"],
                "weight_pct": [6.0, 4.0, 9.0, 1.5],
                "contribution_pct": [1.0, 2.0, 3.0, 4.0],
            }
        )

        exposure = _build_single_etf_dimension_exposure(combined_holdings, "SWDA", "company")

        self.assertEqual(exposure["company"].tolist(), ["Apple", "Microsoft"])
        self.assertEqual(exposure["weight_pct"].round(2).tolist(), [7.5, 4.0])
        self.assertAlmostEqual(exposure["weight_pct"].sum(), 11.5, places=6)

    def test_build_report_exposes_single_etf_analysis_inputs(self) -> None:
        report = build_report(snapshot_date="20260408")

        self.assertEqual(report["single_etf_options"], ["SWDA", "EMIM", "WSML"])
        swda = report["single_etf_analysis"]["SWDA"]
        self.assertIn("company_exposure", swda)
        self.assertIn("country_exposure", swda)
        self.assertIn("sector_exposure", swda)
        self.assertTrue((swda["company_exposure"]["weight_pct"] >= 0).all())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m unittest tests.test_portfolio_analysis -v`
Expected: FAIL because `_build_single_etf_dimension_exposure` and the new report fields do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def _build_single_etf_dimension_exposure(
    combined_holdings: pd.DataFrame,
    etf_symbol: str,
    dimension: str,
) -> pd.DataFrame:
    etf_holdings = combined_holdings.loc[combined_holdings["parent_etf"] == etf_symbol].copy()
    if etf_holdings.empty:
        return pd.DataFrame(columns=[dimension, "weight_pct"])

    exposure = (
        etf_holdings.groupby(dimension, dropna=False, as_index=False)["weight_pct"]
        .sum()
        .sort_values(["weight_pct", dimension], ascending=[False, True])
        .reset_index(drop=True)
    )
    return exposure
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m unittest tests.test_portfolio_analysis -v`
Expected: PASS

### Task 2: Publish ETF analysis data in the report

**Files:**
- Modify: `portfolio_analysis.py`
- Test: `tests/test_portfolio_analysis.py`

- [ ] **Step 1: Extend `build_report(...)` to expose ETF analysis data**

```python
    single_etf_options = sorted(combined_holdings["parent_etf"].dropna().unique().tolist())
    single_etf_analysis = {
        etf_symbol: {
            "company_exposure": _build_single_etf_dimension_exposure(combined_holdings, etf_symbol, "company"),
            "country_exposure": _build_single_etf_dimension_exposure(combined_holdings, etf_symbol, "country"),
            "sector_exposure": _build_single_etf_dimension_exposure(combined_holdings, etf_symbol, "sector"),
        }
        for etf_symbol in single_etf_options
    }
```

- [ ] **Step 2: Return the new report fields**

```python
        "single_etf_options": single_etf_options,
        "single_etf_analysis": single_etf_analysis,
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_portfolio_analysis -v`
Expected: PASS

### Task 3: Render the Streamlit tab

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add a weight-based exposure table helper**

```python
def render_weight_table(df: pd.DataFrame, label_column: str, height: int = 360) -> None:
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config={
            label_column: st.column_config.TextColumn(label_column.replace("_", " ").title()),
            "weight_pct": st.column_config.NumberColumn("Weight", format="%.2f%%"),
        },
    )
```

- [ ] **Step 2: Add the new top-level tab**

```python
overview_tab, companies_tab, countries_tab, sectors_tab, overlap_tab, single_etf_tab = st.tabs(
    ["Overview", "Companies", "Countries", "Sectors", "Overlap", "Single ETF Analysis"]
)
```

- [ ] **Step 3: Render the selector and stacked sections**

```python
with single_etf_tab:
    selected_etf = st.selectbox("Select ETF", options=report["single_etf_options"])
    etf_report = report["single_etf_analysis"][selected_etf]

    for title, label_column, data_key in [
        ("Top companies", "company", "company_exposure"),
        ("Top countries", "country", "country_exposure"),
        ("Top sectors", "sector", "sector_exposure"),
    ]:
        st.subheader(f"{selected_etf} {title}")
        section_cols = st.columns([1.35, 1])
        with section_cols[0]:
            render_bar_chart(
                etf_report[data_key].rename(columns={"weight_pct": "contribution_pct"}),
                label_column,
                f"{selected_etf} {title}",
                top_n,
            )
        with section_cols[1]:
            render_weight_table(etf_report[data_key].head(top_n), label_column)
```

- [ ] **Step 4: Run a smoke check**

Run: `source .venv/bin/activate && python -m py_compile app.py portfolio_analysis.py tests/test_portfolio_analysis.py`
Expected: PASS

### Task 4: Final verification

**Files:**
- Modify: `portfolio_analysis.py`
- Modify: `app.py`
- Modify: `tests/test_portfolio_analysis.py`

- [ ] **Step 1: Run the regression tests**

Run: `source .venv/bin/activate && python -m unittest tests.test_portfolio_analysis -v`
Expected: PASS

- [ ] **Step 2: Run a report smoke check**

Run: `source .venv/bin/activate && python - <<'PY'`
Expected: the report prints ETF options plus non-empty company/country/sector exposure tables for `SWDA`.
