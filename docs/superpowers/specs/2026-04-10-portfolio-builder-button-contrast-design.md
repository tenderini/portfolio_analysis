# Portfolio Builder Button Contrast Design

## Goal

Improve the readability of the `Portfolio Builder` action buttons in the Streamlit app. The current button treatment appears too light against the existing palette, which makes the labels hard to read for controls such as `Add ETF`, `Remove ETF`, `Save portfolio`, and ETF-specific `Refresh` actions.

## Recommended Approach

Update the shared button styling in `src/portfolio_analysis_app/app_theme.py` so Streamlit buttons use a darker surface with light foreground text, while keeping the existing teal accent as the interactive highlight. This keeps the UI aligned with the dark dashboard theme and fixes the contrast issue without introducing one-off overrides inside the builder view.

## Scope

- Change the base `.stButton > button` background from the current bright teal gradient to a dark elevated surface.
- Set button text to the theme's light foreground color.
- Preserve the teal accent through border, shadow, and hover/focus states so buttons still feel active and consistent with the rest of the app.
- Cover the styling contract with a test in `tests/test_app_theme.py`.

## Implementation Notes

- Prefer theme-level CSS changes over targeted selectors in `app.py` because the affected controls all use the standard Streamlit button component.
- Keep the button styling generic enough that other buttons remain legible if they inherit the same theme.
- Avoid changing layout, labels, or Portfolio Builder logic; this is a visual contrast fix only.

## Error Handling And Risk

- Main risk: changing the global button style could affect other buttons outside the builder. The design keeps the styling within the current dark visual system to minimize regressions.
- No data flow or persistence behavior changes are expected.

## Testing

- Update or add a unit test asserting that `build_theme_css()` includes the darker button background and readable light foreground color.
- Run the focused theme test module after the change.
