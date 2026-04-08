from __future__ import annotations


def build_summary_metrics(summary: dict) -> list[dict[str, str]]:
    return [
        {"label": "Companies", "value": f'{summary["unique_companies"]:,}'},
        {"label": "Countries", "value": f'{summary["unique_countries"]:,}'},
        {"label": "Sectors", "value": f'{summary["unique_sectors"]:,}'},
        {"label": "Portfolio total", "value": f'{summary["portfolio_total_pct"]:.2f}%'},
    ]
