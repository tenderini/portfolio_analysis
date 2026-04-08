# ETF Composition Pie Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fixed ETF composition section to the Streamlit dashboard that shows the PIE portfolio split across `SWDA`, `EMIM`, and `WSML`.

**Architecture:** Compute a small `etf_composition` dataframe in `portfolio_analysis.py` from `combined_holdings`, then render it in `app.py` as a dedicated `Portfolio Composition` section above `Top Exposures`. Keep the change narrow by adding one report helper, one chart helper, and one small table renderer.

**Tech Stack:** Python, pandas, Streamlit, optional Plotly

---

### Task 1: Add the report-layer regression test

**Files:**
- Create: `tests/test_portfolio_analysis.py`
- Test: `tests/test_portfolio_analysis.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

import pandas as pd

from portfolio_analysis import _build_etf_composition


class BuildEtfCompositionTests(unittest.TestCase):
    def test_build_etf_composition_collapses_duplicate_holdings_to_one_row_per_etf(self) -> None:
        combined_holdings = pd.DataFrame(
            {
                "parent_etf": ["SWDA", "SWDA", "EMIM", "WSML"],
                "pie_weight": [0.78, 0.78, 0.12, 0.10],
                "company": ["A", "B", "C", "D"],
                "contribution_pct": [1.0, 2.0, 3.0, 4.0],
            }
        )

        composition = _build_etf_composition(combined_holdings)

        self.assertEqual(composition["parent_etf"].tolist(), ["SWDA", "EMIM", "WSML"])
        self.assertEqual(composition["allocation_pct"].round(2).tolist(), [78.0, 12.0, 10.0])
        self.assertAlmostEqual(composition["allocation_pct"].sum(), 100.0, places=6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m unittest tests.test_portfolio_analysis -v`
Expected: FAIL with `ImportError` or `AttributeError` because `_build_etf_composition` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def _build_etf_composition(combined_holdings: pd.DataFrame) -> pd.DataFrame:
    if combined_holdings.empty:
        return pd.DataFrame(columns=["parent_etf", "allocation_pct"])

    composition = (
        combined_holdings.groupby("parent_etf", as_index=False)["pie_weight"]
        .max()
        .rename(columns={"pie_weight": "allocation_pct"})
    )
    composition["allocation_pct"] = composition["allocation_pct"].fillna(0.0) * 100.0
    return composition.sort_values(
        ["allocation_pct", "parent_etf"],
        ascending=[False, True],
    ).reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m unittest tests.test_portfolio_analysis -v`
Expected: PASS

### Task 2: Expose ETF composition in the report

**Files:**
- Modify: `portfolio_analysis.py`
- Test: `tests/test_portfolio_analysis.py`

- [ ] **Step 1: Extend the test to cover report output**

```python
from portfolio_analysis import build_report


    def test_build_report_exposes_etf_composition(self) -> None:
        report = build_report(snapshot_date="20260408")

        self.assertIn("etf_composition", report)
        self.assertEqual(report["etf_composition"]["parent_etf"].tolist(), ["SWDA", "EMIM", "WSML"])
        self.assertAlmostEqual(report["etf_composition"]["allocation_pct"].sum(), 100.0, places=6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m unittest tests.test_portfolio_analysis -v`
Expected: FAIL because `build_report(...)` does not yet return `etf_composition`.

- [ ] **Step 3: Write minimal implementation**

```python
    etf_composition = _build_etf_composition(combined_holdings)

    return {
        ...
        "etf_composition": etf_composition,
        ...
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m unittest tests.test_portfolio_analysis -v`
Expected: PASS

### Task 3: Render the Streamlit composition section

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add a pie-chart helper and composition table renderer**

```python
def render_pie_chart(data: pd.DataFrame, names_column: str, values_column: str, title: str) -> None:
    if data.empty:
        st.info("No data available for this view.")
        return
    if px is None:
        st.info("Install plotly to view the ETF composition pie chart.")
        return

    fig = px.pie(
        data,
        names=names_column,
        values=values_column,
        title=title,
        hole=0.35,
        color=names_column,
    )
    fig.update_traces(textposition="inside", texttemplate="%{label}<br>%{value:.2f}%")
    st.plotly_chart(fig, use_container_width=True)
```

- [ ] **Step 2: Render the new Overview section**

```python
with overview_tab:
    st.subheader("Portfolio Composition")
    composition_cols = st.columns([1.15, 0.85])
    with composition_cols[0]:
        render_pie_chart(report["etf_composition"], "parent_etf", "allocation_pct", "ETF allocation")
    with composition_cols[1]:
        st.dataframe(
            report["etf_composition"],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Top Exposures")
```

- [ ] **Step 3: Run a local smoke check**

Run: `source .venv/bin/activate && python - <<'PY'`
Expected: `build_report("20260408")["etf_composition"]` prints three ETFs totaling `100.0`.

### Task 4: Final verification

**Files:**
- Modify: `portfolio_analysis.py`
- Modify: `app.py`
- Create: `tests/test_portfolio_analysis.py`

- [ ] **Step 1: Run the regression test suite**

Run: `source .venv/bin/activate && python -m unittest tests.test_portfolio_analysis -v`
Expected: PASS

- [ ] **Step 2: Run a dashboard-level smoke check**

Run: `source .venv/bin/activate && python - <<'PY'`
Expected: report contains `etf_composition` with `SWDA`, `EMIM`, `WSML`, and the allocations sum to `100.0`.
