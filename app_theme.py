from __future__ import annotations

from typing import Iterable


DARK_ETF_COLOR_MAP = {
    "SWDA": "#4ecdc4",
    "EMIM": "#7dd3fc",
    "WSML": "#f4b860",
}

BAR_COLOR_SCALE = ["#16313a", "#24505d", "#4ecdc4"]
PLOT_BACKGROUND = "#111827"
PAPER_BACKGROUND = "rgba(0, 0, 0, 0)"
TEXT_PRIMARY = "#e5eef5"
TEXT_SECONDARY = "#8aa0b5"
GRID_X = "rgba(138, 160, 181, 0.18)"
GRID_Y = "rgba(138, 160, 181, 0.10)"


def build_theme_css() -> str:
    return """
    <style>
      :root {
        --bg-main: #071018;
        --bg-gradient-top: #0c1620;
        --bg-surface: #111827;
        --bg-elevated: #17212b;
        --bg-sidebar: #0d141d;
        --accent: #4ecdc4;
        --accent-strong: #7df9ee;
        --accent-soft: rgba(78, 205, 196, 0.14);
        --text-primary: #e5eef5;
        --text-secondary: #8aa0b5;
        --border: rgba(148, 163, 184, 0.16);
        --shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
        color-scheme: dark;
      }

      .stApp {
        background:
          radial-gradient(circle at top right, rgba(78, 205, 196, 0.12), transparent 28%),
          linear-gradient(180deg, var(--bg-gradient-top) 0%, var(--bg-main) 55%);
        color: var(--text-primary);
      }

      [data-testid="stToolbar"],
      header[data-testid="stHeader"],
      #MainMenu {
        display: none !important;
      }

      .block-container {
        padding-top: 1.35rem;
        padding-bottom: 2.25rem;
      }

      .dashboard-hero,
      .dashboard-banner {
        background:
          linear-gradient(140deg, rgba(23, 33, 43, 0.96) 0%, rgba(17, 24, 39, 0.94) 60%, rgba(12, 22, 32, 0.98) 100%);
        border: 1px solid var(--border);
        border-radius: 24px;
        padding: 1.5rem 1.65rem;
        margin-bottom: 1.1rem;
        box-shadow: var(--shadow);
        position: relative;
        overflow: hidden;
      }

      .dashboard-hero::before,
      .dashboard-banner::before {
        content: "";
        position: absolute;
        inset: -40% auto auto 60%;
        width: 260px;
        height: 260px;
        background: radial-gradient(circle, rgba(78, 205, 196, 0.18) 0%, rgba(78, 205, 196, 0) 70%);
        pointer-events: none;
      }

      .dashboard-banner h1 {
        color: var(--text-primary);
        font-size: 2.1rem;
        line-height: 1.08;
        letter-spacing: -0.02em;
        margin: 0;
      }

      .dashboard-banner p {
        color: var(--text-secondary);
        font-size: 0.98rem;
        margin: 0.55rem 0 0 0;
        max-width: 60rem;
      }

      .content-panel {
        background: rgba(17, 24, 39, 0.72);
        border: 1px solid var(--border);
        border-radius: 22px;
        padding: 1rem 1rem 0.25rem 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 20px 45px rgba(0, 0, 0, 0.18);
        backdrop-filter: blur(8px);
      }

      [data-testid="stSidebar"] {
        background:
          linear-gradient(180deg, rgba(13, 20, 29, 0.98) 0%, rgba(9, 15, 22, 0.98) 100%);
        border-right: 1px solid var(--border);
      }

      [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
      [data-testid="stSidebar"] label,
      [data-testid="stSidebar"] p,
      [data-testid="stSidebar"] span {
        color: var(--text-primary);
      }

      [data-testid="stSidebar"] .stButton > button,
      [data-testid="stSidebar"] .stTextInput input,
      [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"],
      [data-testid="stSidebar"] .stSlider {
        border-radius: 14px;
      }

      .stButton > button {
        background: linear-gradient(135deg, rgba(78, 205, 196, 0.95) 0%, rgba(44, 164, 160, 0.92) 100%);
        color: #041016;
        border: 0;
        font-weight: 700;
        box-shadow: 0 12px 24px rgba(78, 205, 196, 0.2);
      }

      .stButton > button:hover {
        filter: brightness(1.04);
      }

      .stTextInput input,
      .stSelectbox [data-baseweb="select"] > div,
      .stMultiSelect [data-baseweb="select"] > div {
        background: rgba(17, 24, 39, 0.92);
        color: var(--text-primary);
        border: 1px solid var(--border);
      }

      .stTextInput input:focus,
      .stSelectbox [data-baseweb="select"] > div:focus-within,
      .stMultiSelect [data-baseweb="select"] > div:focus-within {
        border-color: rgba(78, 205, 196, 0.55);
        box-shadow: 0 0 0 1px rgba(78, 205, 196, 0.22);
      }

      [data-baseweb="tab-list"] {
        gap: 0.45rem;
        background: rgba(11, 19, 28, 0.72);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 0.35rem;
      }

      [data-baseweb="tab"] {
        background: transparent;
        color: var(--text-secondary);
        border-radius: 12px;
        border: 0;
        padding: 0.5rem 0.9rem;
        font-weight: 600;
      }

      [data-baseweb="tab"][aria-selected="true"] {
        background: rgba(78, 205, 196, 0.12);
        color: var(--text-primary);
        box-shadow: inset 0 0 0 1px rgba(78, 205, 196, 0.16);
      }

      [data-baseweb="tab-highlight"] {
        background: transparent !important;
        height: 0 !important;
      }

      .stPlotlyChart {
        background: rgba(17, 24, 39, 0.88);
        border: 1px solid var(--border);
        border-radius: 22px;
        padding: 0.35rem 0.35rem 0.1rem 0.35rem;
        box-shadow: 0 16px 34px rgba(0, 0, 0, 0.14);
        overflow: hidden;
      }

      [data-testid="stMetric"] {
        background: linear-gradient(180deg, rgba(23, 33, 43, 0.9) 0%, rgba(17, 24, 39, 0.84) 100%);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 0.45rem 0.75rem;
        min-height: 100%;
        box-shadow: 0 18px 34px rgba(0, 0, 0, 0.16);
      }

      [data-testid="stMetricLabel"] {
        color: var(--text-secondary);
      }

      [data-testid="stMetricValue"] {
        color: var(--text-primary);
      }

      div[data-testid="stDataFrame"] {
        border: 1px solid var(--border);
        border-radius: 18px;
        overflow: hidden;
      }

      div[data-testid="stDataFrame"] [role="columnheader"] {
        background: rgba(11, 19, 28, 0.98);
        color: var(--text-primary);
      }

      div[data-testid="stDataFrame"] [role="gridcell"] {
        background: rgba(17, 24, 39, 0.98);
        color: var(--text-primary);
        border-color: rgba(148, 163, 184, 0.1);
      }

      .stAlert,
      [data-testid="stExpander"] {
        background: rgba(17, 24, 39, 0.82);
        border: 1px solid var(--border);
        color: var(--text-primary);
        border-radius: 18px;
      }

      .stCaption,
      [data-testid="stMarkdownContainer"] p,
      [data-testid="stMarkdownContainer"] li {
        color: var(--text-secondary);
      }

      h2, h3 {
        color: var(--text-primary);
        letter-spacing: -0.01em;
      }
    </style>
    """


def build_bar_value_axis_range(values: Iterable[float]) -> list[float]:
    numeric_values = [float(value) for value in values]
    if not numeric_values:
        return [0.0, 1.0]

    max_value = max(numeric_values)
    if max_value <= 0:
        return [0.0, 1.0]

    padding = max(max_value * 0.18, 1.0)
    return [0.0, max_value + padding]


def apply_dark_figure_layout(fig, title: str | None = None, height: int | None = None):
    layout = dict(
        height=height,
        paper_bgcolor=PAPER_BACKGROUND,
        plot_bgcolor=PLOT_BACKGROUND,
        font={"color": TEXT_PRIMARY},
        margin={"l": 0, "r": 12, "t": 56, "b": 12},
        xaxis={"gridcolor": GRID_X, "zeroline": False},
        yaxis={"gridcolor": GRID_Y, "zeroline": False},
    )
    if title is not None:
        layout["title"] = title
    fig.update_layout(**layout)
    return fig
