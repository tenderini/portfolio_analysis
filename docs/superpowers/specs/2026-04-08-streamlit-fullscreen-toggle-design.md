# Streamlit Fullscreen Layout Toggle Design

## Summary

Add a user-facing toggle that lets the Streamlit dashboard switch between the current padded layout and a wider fullscreen layout.

The default experience stays unchanged. Users can enable fullscreen mode from the sidebar when they want charts, tables, and tab content to use more of the browser width.

## Goals

- Preserve the current dashboard appearance by default.
- Let users opt into a wider layout without reloading or navigating away.
- Keep the change small and localized to existing layout and theme code.
- Avoid changing data-loading, chart, or table behavior.

## Non-Goals

- Hiding the Streamlit sidebar.
- Forcing the browser into native fullscreen mode.
- Reworking dashboard content structure or responsive breakpoints.
- Adding persistent user preferences outside the current session state.

## Current Context

The app already calls `st.set_page_config(layout="wide")` in `app.py`, but the custom theme CSS still controls the effective content width and padding. This means the page is wide in Streamlit terms, yet still visually constrained by `.block-container` styling in `app_theme.py`.

## Proposed Approach

### User Interface

Add a new sidebar control:

- Label: `Full screen layout`
- Type: `st.toggle`
- Default: `False`

Placement should be below the existing filters and above the refresh button because it changes presentation, not data.

### Behavior

When the toggle is off:

- Keep the existing padded layout and spacing.

When the toggle is on:

- Expand the main content area to use more of the available browser width.
- Reduce left and right padding on the main content container.
- Leave the sidebar visible and unchanged.
- Keep existing charts and tables using container width as they do now.

This is a layout toggle, not a browser fullscreen feature. The browser window and Streamlit sidebar remain under user control.

### Implementation

Update `build_theme_css` in `app_theme.py` to accept a boolean flag for fullscreen layout.

The function will return the existing theme CSS plus one of two `.block-container` variants:

- Default mode: current top and bottom padding plus the current constrained content width.
- Fullscreen mode: same vertical spacing, reduced horizontal padding, and a larger or unconstrained max width so the main pane can stretch.

Update `app.py` to:

1. Render the sidebar toggle.
2. Pass the toggle value into `build_theme_css`.
3. Apply the resulting CSS with `st.markdown(..., unsafe_allow_html=True)`.

No changes are needed in the dashboard rendering helpers because the charts and dataframes already use container width.

## Data Flow

1. Streamlit renders the sidebar controls.
2. The user turns `Full screen layout` on or off.
3. The toggle value is read during app execution.
4. `build_theme_css(fullscreen=...)` returns the appropriate layout CSS.
5. Streamlit re-renders the page using the selected layout styling.

## Error Handling

There is no new external dependency or network behavior.

If the toggle is unavailable for any reason, the app should continue to render in the default layout because the CSS function should default to the existing mode.

## Testing

Add unit coverage in `tests/test_app_theme.py` to verify:

- The default CSS still includes the standard container styling.
- Fullscreen mode produces different `.block-container` width or padding rules from default mode.

No behavioral test is needed for Streamlit widget wiring in this change because the app already applies generated CSS through a single `st.markdown` call, and the risk is concentrated in CSS generation.

## Risks and Mitigations

- Risk: Fullscreen spacing could make some sections feel too stretched on very large displays.
  Mitigation: Keep some horizontal padding in fullscreen mode rather than making the layout edge-to-edge.

- Risk: CSS selectors could unintentionally affect other Streamlit containers.
  Mitigation: Limit the change to the existing `.block-container` rule and avoid broader selector changes.

## Rollout Notes

This can ship as a single small change with no migration steps. Existing users will see the current layout unless they enable the new toggle.
