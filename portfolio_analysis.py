from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pandas as pd


DATA_DIR = Path(__file__).resolve().parent / "data"
TOP_CONCENTRATION_BUCKETS = (10, 20, 50)
REQUIRED_SNAPSHOT_FILES = {
    "company_exposure": "PIE_company_exposure_{date}.csv",
    "country_exposure": "PIE_country_exposure_{date}.csv",
    "sector_exposure": "PIE_sector_exposure_{date}.csv",
    "combined_holdings": "PIE_combined_holdings_detail_{date}.parquet",
}


def list_available_snapshot_dates(data_dir: Path | str = DATA_DIR) -> list[str]:
    data_path = Path(data_dir)
    pattern = re.compile(r"^PIE_company_exposure_(\d{8})\.csv$")
    dates: list[str] = []

    for file_path in data_path.glob("PIE_company_exposure_*.csv"):
        match = pattern.match(file_path.name)
        if not match:
            continue
        snapshot_date = match.group(1)
        files = get_snapshot_paths(snapshot_date, data_path)
        if all(path.exists() for path in files.values()):
            dates.append(snapshot_date)

    return sorted(set(dates), reverse=True)


def get_latest_snapshot_date(data_dir: Path | str = DATA_DIR) -> str:
    dates = list_available_snapshot_dates(data_dir)
    if not dates:
        raise FileNotFoundError(f"No complete PIE snapshots found in {Path(data_dir)}")
    return dates[0]


def get_snapshot_paths(snapshot_date: str, data_dir: Path | str = DATA_DIR) -> dict[str, Path]:
    data_path = Path(data_dir)
    return {
        key: data_path / pattern.format(date=snapshot_date)
        for key, pattern in REQUIRED_SNAPSHOT_FILES.items()
    }


def load_snapshot_inputs(snapshot_date: str | None = None, data_dir: Path | str = DATA_DIR) -> dict[str, Any]:
    resolved_date = snapshot_date or get_latest_snapshot_date(data_dir)
    files = get_snapshot_paths(resolved_date, data_dir)

    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing snapshot files for {resolved_date}: {missing}")

    company_exposure = _read_exposure_csv(files["company_exposure"], "company")
    country_exposure = _read_exposure_csv(files["country_exposure"], "country", unknown_label="Unknown")
    sector_exposure = _read_exposure_csv(files["sector_exposure"], "sector", unknown_label="Unknown")
    combined_holdings = _read_combined_holdings(files["combined_holdings"])

    return {
        "snapshot_date": resolved_date,
        "files": files,
        "source_company_exposure": company_exposure,
        "source_country_exposure": country_exposure,
        "source_sector_exposure": sector_exposure,
        "combined_holdings": combined_holdings,
    }


def build_report(snapshot_date: str | None = None, data_dir: Path | str = DATA_DIR) -> dict[str, Any]:
    snapshot_inputs = load_snapshot_inputs(snapshot_date=snapshot_date, data_dir=data_dir)
    combined_holdings = snapshot_inputs["combined_holdings"]

    single_etf_options = sorted(combined_holdings["parent_etf"].dropna().unique().tolist())
    single_etf_analysis = {
        etf_symbol: {
            "company_exposure": _build_single_etf_dimension_exposure(combined_holdings, etf_symbol, "company"),
            "country_exposure": _build_single_etf_dimension_exposure(combined_holdings, etf_symbol, "country"),
            "sector_exposure": _build_single_etf_dimension_exposure(combined_holdings, etf_symbol, "sector"),
        }
        for etf_symbol in single_etf_options
    }
    etf_composition = _build_etf_composition(combined_holdings)
    company_exposure = _build_dimension_exposure(
        combined_holdings,
        "company",
        fallback=snapshot_inputs["source_company_exposure"],
    )
    country_exposure = _build_dimension_exposure(
        combined_holdings,
        "country",
        fallback=snapshot_inputs["source_country_exposure"],
    )
    sector_exposure = _build_dimension_exposure(
        combined_holdings,
        "sector",
        fallback=snapshot_inputs["source_sector_exposure"],
    )

    company_etf_breakdown = _build_etf_breakdown(combined_holdings, "company")
    country_etf_breakdown = _build_etf_breakdown(combined_holdings, "country")
    sector_etf_breakdown = _build_etf_breakdown(combined_holdings, "sector")
    country_company_drivers = _build_company_drivers(combined_holdings, "country")
    sector_company_drivers = _build_company_drivers(combined_holdings, "sector")
    overlap_table = _build_overlap_table(combined_holdings)
    concentration_metrics = _build_concentration_metrics(
        company_exposure=company_exposure,
        country_exposure=country_exposure,
        sector_exposure=sector_exposure,
    )

    return {
        "snapshot_date": snapshot_inputs["snapshot_date"],
        "files": snapshot_inputs["files"],
        "combined_holdings": combined_holdings,
        "etf_composition": etf_composition,
        "single_etf_options": single_etf_options,
        "single_etf_analysis": single_etf_analysis,
        "company_exposure": company_exposure,
        "country_exposure": country_exposure,
        "sector_exposure": sector_exposure,
        "company_etf_breakdown": company_etf_breakdown,
        "country_etf_breakdown": country_etf_breakdown,
        "sector_etf_breakdown": sector_etf_breakdown,
        "country_company_drivers": country_company_drivers,
        "sector_company_drivers": sector_company_drivers,
        "overlap_table": overlap_table,
        "concentration_metrics": concentration_metrics,
        "summary": {
            "total_holdings_count": int(len(combined_holdings)),
            "unique_companies": int(company_exposure["company"].nunique()),
            "unique_countries": int(country_exposure["country"].nunique()),
            "unique_sectors": int(sector_exposure["sector"].nunique()),
            "portfolio_total_pct": float(company_exposure["contribution_pct"].sum()),
            "overlap_count": int(len(overlap_table)),
        },
    }


def filter_company_exposure(company_exposure: pd.DataFrame, search_text: str = "") -> pd.DataFrame:
    cleaned_search = search_text.strip().casefold()
    if not cleaned_search:
        return company_exposure.copy()

    company_series = company_exposure["company"].astype(str).str.casefold()
    return company_exposure.loc[company_series.str.contains(cleaned_search, na=False)].reset_index(drop=True)


def get_company_drilldown(company_etf_breakdown: pd.DataFrame, company: str) -> pd.DataFrame:
    if not company:
        return company_etf_breakdown.iloc[0:0].copy()

    return (
        company_etf_breakdown.loc[company_etf_breakdown["company"] == company]
        .sort_values(["contribution_pct", "parent_etf"], ascending=[False, True])
        .reset_index(drop=True)
    )


def get_dimension_drilldown(
    etf_breakdown: pd.DataFrame,
    company_drivers: pd.DataFrame,
    dimension: str,
    value: str,
) -> dict[str, pd.DataFrame]:
    if not value:
        empty_breakdown = etf_breakdown.iloc[0:0].copy()
        empty_drivers = company_drivers.iloc[0:0].copy()
        return {"etf_breakdown": empty_breakdown, "top_companies": empty_drivers}

    etf_view = (
        etf_breakdown.loc[etf_breakdown[dimension] == value]
        .sort_values(["contribution_pct", "parent_etf"], ascending=[False, True])
        .reset_index(drop=True)
    )
    driver_view = (
        company_drivers.loc[company_drivers[dimension] == value]
        .sort_values(["contribution_pct", "company"], ascending=[False, True])
        .reset_index(drop=True)
    )
    return {"etf_breakdown": etf_view, "top_companies": driver_view}


def _read_exposure_csv(
    file_path: Path,
    label_column: str,
    unknown_label: str | None = None,
) -> pd.DataFrame:
    exposure = pd.read_csv(file_path)
    if label_column not in exposure.columns or "contribution_pct" not in exposure.columns:
        raise ValueError(f"Unexpected exposure schema in {file_path}")

    exposure = exposure[[label_column, "contribution_pct"]].copy()
    exposure["contribution_pct"] = pd.to_numeric(exposure["contribution_pct"], errors="coerce").fillna(0.0)
    exposure[label_column] = _clean_text_series(exposure[label_column], unknown_label=unknown_label)
    exposure = exposure[exposure["contribution_pct"] > 0].reset_index(drop=True)
    return exposure.sort_values("contribution_pct", ascending=False).reset_index(drop=True)


def _read_combined_holdings(file_path: Path) -> pd.DataFrame:
    combined = pd.read_parquet(file_path).copy()
    expected_columns = {
        "company",
        "country",
        "sector",
        "weight_pct",
        "pie_weight",
        "contribution_pct",
        "parent_etf",
    }
    missing_columns = expected_columns.difference(combined.columns)
    if missing_columns:
        raise ValueError(f"Missing columns in {file_path}: {sorted(missing_columns)}")

    combined["company"] = _clean_text_series(combined["company"], unknown_label="Unknown")
    combined["country"] = _clean_text_series(combined["country"], unknown_label="Unknown")
    combined["sector"] = _clean_text_series(combined["sector"], unknown_label="Unknown")
    combined["parent_etf"] = _clean_text_series(combined["parent_etf"], unknown_label="Unknown")
    combined["weight_pct"] = pd.to_numeric(combined["weight_pct"], errors="coerce").fillna(0.0)
    combined["pie_weight"] = pd.to_numeric(combined["pie_weight"], errors="coerce").fillna(0.0)
    combined["contribution_pct"] = pd.to_numeric(combined["contribution_pct"], errors="coerce").fillna(0.0)

    combined = combined.loc[combined["contribution_pct"] > 0].reset_index(drop=True)
    return combined.sort_values("contribution_pct", ascending=False).reset_index(drop=True)


def _build_dimension_exposure(
    combined_holdings: pd.DataFrame,
    dimension: str,
    fallback: pd.DataFrame | None = None,
) -> pd.DataFrame:
    exposure = (
        combined_holdings.groupby(dimension, dropna=False, as_index=False)["contribution_pct"]
        .sum()
        .sort_values(["contribution_pct", dimension], ascending=[False, True])
        .reset_index(drop=True)
    )

    if not exposure.empty:
        return exposure

    if fallback is not None:
        return fallback.copy()

    return pd.DataFrame(columns=[dimension, "contribution_pct"])


def _build_etf_breakdown(combined_holdings: pd.DataFrame, dimension: str) -> pd.DataFrame:
    breakdown = (
        combined_holdings.groupby([dimension, "parent_etf"], as_index=False)
        .agg(
            contribution_pct=("contribution_pct", "sum"),
            underlying_weight_pct=("weight_pct", "sum"),
            line_items=("company", "size"),
        )
        .sort_values([dimension, "contribution_pct", "parent_etf"], ascending=[True, False, True])
        .reset_index(drop=True)
    )
    return breakdown


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


def _build_company_drivers(combined_holdings: pd.DataFrame, dimension: str) -> pd.DataFrame:
    return (
        combined_holdings.groupby([dimension, "company"], as_index=False)["contribution_pct"]
        .sum()
        .sort_values([dimension, "contribution_pct", "company"], ascending=[True, False, True])
        .reset_index(drop=True)
    )


def _build_etf_composition(combined_holdings: pd.DataFrame) -> pd.DataFrame:
    if combined_holdings.empty:
        return pd.DataFrame(columns=["parent_etf", "allocation_pct"])

    composition = (
        combined_holdings.groupby("parent_etf", as_index=False)["pie_weight"]
        .max()
        .rename(columns={"pie_weight": "allocation_pct"})
    )
    composition["allocation_pct"] = pd.to_numeric(
        composition["allocation_pct"],
        errors="coerce",
    ).fillna(0.0) * 100.0
    return composition.sort_values(
        ["allocation_pct", "parent_etf"],
        ascending=[False, True],
    ).reset_index(drop=True)


def _build_overlap_table(combined_holdings: pd.DataFrame) -> pd.DataFrame:
    overlap_source = combined_holdings.loc[
        ~combined_holdings["company"].str.contains("cash", case=False, na=False)
    ].copy()
    overlap_base = (
        overlap_source.groupby("company", as_index=False)
        .agg(
            total_contribution_pct=("contribution_pct", "sum"),
            num_etfs=("parent_etf", "nunique"),
        )
    )
    overlap_base = overlap_base.loc[overlap_base["num_etfs"] > 1].copy()

    if overlap_base.empty:
        return overlap_base

    overlap_etfs = (
        overlap_source.groupby("company")["parent_etf"]
        .agg(lambda values: ", ".join(sorted(set(values))))
        .reset_index(name="etfs")
    )
    overlap_pivot = (
        overlap_source.pivot_table(
            index="company",
            columns="parent_etf",
            values="contribution_pct",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
    )
    overlap_pivot.columns.name = None

    overlap_table = overlap_base.merge(overlap_etfs, on="company", how="left").merge(
        overlap_pivot,
        on="company",
        how="left",
    )
    return overlap_table.sort_values(
        ["num_etfs", "total_contribution_pct", "company"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def _build_concentration_metrics(
    company_exposure: pd.DataFrame,
    country_exposure: pd.DataFrame,
    sector_exposure: pd.DataFrame,
) -> pd.DataFrame:
    frames = {
        "Company": company_exposure,
        "Country": country_exposure,
        "Sector": sector_exposure,
    }
    rows = []

    for dimension, exposure in frames.items():
        decimal_weights = exposure["contribution_pct"].fillna(0.0) / 100.0
        hhi = float((decimal_weights ** 2).sum())
        row = {
            "dimension": dimension,
            "items": int(len(exposure)),
            "hhi": hhi,
            "effective_holdings": float(1.0 / hhi) if hhi > 0 else 0.0,
        }
        for bucket in TOP_CONCENTRATION_BUCKETS:
            row[f"top_{bucket}_pct"] = float(exposure.head(bucket)["contribution_pct"].sum())
        rows.append(row)

    return pd.DataFrame(rows)


def _clean_text_series(series: pd.Series, unknown_label: str | None = None) -> pd.Series:
    cleaned = series.fillna("").astype(str).str.strip()
    if unknown_label is None:
        return cleaned.replace({"nan": "", "None": ""})
    return cleaned.replace({"": unknown_label, "nan": unknown_label, "None": unknown_label})
