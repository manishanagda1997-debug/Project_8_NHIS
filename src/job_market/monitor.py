"""Monthly and weekly market monitoring tables for the dashboard (Task 6, decision D-036).

Only the reliable time-series window is summarised (16 February - 23 March
2024 in the current extract); the scattered earlier days are never mixed in.
When a newer extract with more days is rebuilt, new months and weeks appear
automatically: nothing here names a month.

Comparisons are made per day and as shares, never as raw totals, because the
observed months can be partial:

* ``jobs_per_day``: jobs divided by the observed days;
* ``jobs_per_day_weekday_std``: the average of the seven weekday means, so a
  month with more Fridays or Saturdays is not favoured (NaN when a weekday is
  missing from the month);
* ``effective_countries``: 1 / HHI of the client-country shares (known
  countries only). Unlike a count of distinct countries, it does not grow
  just because a period has more days or more jobs;
* ``median_hourly_rate``: the midpoint of complete stated hourly ranges, for
  jobs eligible for hourly-rate analysis (Notebook 04's population).
"""

from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

COLUMNS = ["row_id", "posted_date", "iso_week", "contract_type", "country", "hourly_mid",
           "eligible_for_hourly_rate_analysis", "primary_category"]


def hhi_effective(country: pd.Series) -> tuple[float, float]:
    """Herfindahl index of the known-country shares and its effective number (1 / HHI)."""
    known = country.dropna()
    if known.empty:
        return np.nan, np.nan
    shares = known.value_counts(normalize=True)
    hhi = float((shares ** 2).sum())
    return hhi, 1.0 / hhi


def weekday_standardized(daily: pd.DataFrame) -> float:
    """Average of the seven weekday means of daily jobs; NaN when a weekday is missing."""
    means = daily.groupby(daily["date"].dt.dayofweek)["jobs"].mean()
    return float(means.mean()) if len(means) == 7 else np.nan


def period_summary(part: pd.DataFrame) -> dict:
    daily = part.groupby("posted_date").size().rename("jobs").reset_index().rename(columns={"posted_date": "date"})
    rates = part.loc[part["eligible_for_hourly_rate_analysis"], "hourly_mid"].dropna()
    hhi, effective = hhi_effective(part["country"])
    return {
        "first_day": daily["date"].min().strftime("%Y-%m-%d"),
        "last_day": daily["date"].max().strftime("%Y-%m-%d"),
        "days_observed": int(len(daily)),
        "jobs": int(len(part)),
        "jobs_per_day": float(len(part) / len(daily)),
        "jobs_per_day_weekday_std": weekday_standardized(daily),
        "hourly_share_pct": float(100 * part["contract_type"].eq("hourly").mean()),
        "median_hourly_rate": float(rates.median()) if len(rates) else np.nan,
        "hourly_rate_jobs": int(len(rates)),
        "known_country_pct": float(100 * part["country"].notna().mean()),
        "hhi": hhi,
        "effective_countries": effective,
    }


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame[COLUMNS].copy()
    out["posted_date"] = pd.to_datetime(out["posted_date"])
    out["month"] = out["posted_date"].dt.strftime("%Y-%m")
    out["iso_week"] = out["iso_week"].astype(str)
    out["contract_type"] = out["contract_type"].astype(str)
    out["primary_category"] = out["primary_category"].astype(str)
    out["country"] = out["country"].astype(object).where(out["country"].notna(), None)
    return out


def monthly_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for month, part in frame.groupby("month", sort=True):
        year, number = map(int, month.split("-"))
        days_in_month = calendar.monthrange(year, number)[1]
        summary = period_summary(part)
        rows.append({"month": month, "label": f"{calendar.month_abbr[number]} {year}", "days_in_month": days_in_month,
                     **summary, "partial": summary["days_observed"] < days_in_month})
    table = pd.DataFrame(rows)
    if len(table):
        table["label"] = [f"{r.label} ({r.days_observed} days)" if r.partial else r.label for r in table.itertuples()]
    return table


def weekly_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for week, part in frame.groupby("iso_week", sort=True):
        summary = period_summary(part)
        rows.append({"iso_week": week, "week_start": (part["posted_date"].min()
                                                      - pd.to_timedelta(part["posted_date"].min().dayofweek, unit="D")
                                                      ).strftime("%Y-%m-%d"),
                     **summary, "complete": summary["days_observed"] == 7})
    return pd.DataFrame(rows)


def group_shares(frame: pd.DataFrame, period: str, column: str, known_only: bool = False) -> pd.DataFrame:
    """Jobs and share (%) of each value of ``column`` within each period."""
    part = frame[frame[column].notna()] if known_only else frame
    counts = part.groupby([period, column]).size().rename("jobs").reset_index()
    counts["share_pct"] = 100 * counts["jobs"] / counts.groupby(period)["jobs"].transform("sum")
    counts["rank"] = counts.groupby(period)["jobs"].rank(method="first", ascending=False).astype(int)
    return counts.sort_values([period, "rank"]).reset_index(drop=True)
