"""Step 6 - trends: emerging categories (Task 2) and online-hiring signals (Task 7).

Decision D-032. Only jobs in the time-series window are used
(``eligible_for_timeseries``: 16 February - 23 March 2024).

Task 2: daily share of each of the 22 job functions, a weekday-adjusted
linear trend with Newey-West standard errors and FDR-adjusted p-values,
reported in percentage points and relative terms. Other / Unclear is
monitored separately, never tested as an "emerging category". Checks: without
possible reposts, without the intraday-gap days, and the first two versus the
last two complete Monday-Sunday weeks. Keywords get the same treatment; new
or rare terms are only counted per week.

Task 7: Upwork is primarily an online marketplace and the data has no
remote/on-site field, so the share of remote jobs cannot be estimated. The
step measures client geography (World Bank regions, concentration), engagement
structure (hourly share, full-time/part-time/long-term mentions) and explicit
work-arrangement mentions in titles.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..config import Settings
from ..io import write_csv
from ..manifest import StepRecord, describe_output
from ..pay import keyword_matrix, select_keywords, title_terms
from ..taxonomy import OTHER
from ..trends import (
    ENGAGEMENT_SIGNALS, SIGNALS, complete_weeks, concentration, daily_shares, region_of, signal_flags,
    trend_fit, trend_table, week_comparison, wilson,
)

NAME = "trends"
DESCRIPTION = "Emerging categories and keywords (Task 2); geography, engagement and work-arrangement signals (Task 7)."

CATEGORY_VARIANTS = (
    ("primary", None),
    ("without_possible_reposts", "possible_repost_3d"),
    ("without_gap_days", "gap_day"),
)


def window_jobs(context: dict[str, Any]) -> pd.DataFrame:
    columns = ["row_id", "title_key", "country", "posted_date", "iso_week", "contract_type", "day_status",
               "possible_repost_3d", "eligible_for_timeseries"]
    frame = context["clean"][columns]
    frame = frame[frame["eligible_for_timeseries"]].merge(
        context["categories"][["row_id", "primary_category"]], on="row_id", how="left", validate="one_to_one")
    frame["primary_category"] = frame["primary_category"].astype(str)
    frame["iso_week"] = frame["iso_week"].astype(str)
    frame["gap_day"] = frame["day_status"].astype(str).eq("intraday_gap")
    return frame.reset_index(drop=True)


def category_results(frame: pd.DataFrame, lag: int, weeks: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = daily_shares(frame, "primary_category")
    main = trend_table(daily[daily["primary_category"] != OTHER], "primary_category", lag)
    for name, exclude in CATEGORY_VARIANTS[1:]:
        part = frame[~frame[exclude].astype(bool)]
        shares = daily_shares(part, "primary_category")
        variant = trend_table(shares[shares["primary_category"] != OTHER], "primary_category", lag)
        main = main.merge(variant[["primary_category", "change_pp", "relative_change_pct"]].rename(columns={
            "change_pp": f"change_pp_{name}", "relative_change_pct": f"relative_change_pct_{name}"}),
            on="primary_category", how="left")
    main = main.merge(week_comparison(frame, "primary_category", weeks), on="primary_category", how="left")
    return daily, main.sort_values("change_pp", ascending=False).reset_index(drop=True)


def other_monitor(daily: pd.DataFrame, lag: int) -> pd.DataFrame:
    part = daily[daily["primary_category"] == OTHER].sort_values("date")
    if part.empty:
        return pd.DataFrame()
    fit = trend_fit(part["share"].to_numpy(), part["date"], lag)
    return pd.DataFrame([{
        "series": "other_unclear share", "mean_pct": 100 * part["share"].mean(),
        "start_pct": 100 * fit["start_level"], "end_pct": 100 * fit["end_level"],
        "change_pp": 100 * fit["change"], "change_low_pp": 100 * fit["change_low"],
        "change_high_pp": 100 * fit["change_high"], "p": fit["p"],
    }])


def keyword_results(frame: pd.DataFrame, rules: dict[str, Any], lag: int, weeks: list[str]) -> pd.DataFrame:
    support = select_keywords(frame["title_key"], int(rules["min_keyword_jobs"]), int(rules["min_keyword_title_keys"]),
                              float(rules["keyword_overlap"]))
    keywords = support["keyword"].tolist()
    if not keywords:
        return pd.DataFrame()
    matrix = keyword_matrix(frame["title_key"].tolist(), keywords).tocsc()
    days = frame["posted_date"].to_numpy()
    totals = frame.groupby("posted_date").size()
    week_codes = frame["iso_week"].to_numpy()
    first, last = np.isin(week_codes, weeks[:2]), np.isin(week_codes, weeks[-2:])
    rows = []
    for j, keyword in enumerate(keywords):
        has = matrix[:, j].toarray().ravel() > 0
        weeks_present = int(pd.Series(week_codes[has]).nunique())
        if weeks_present < int(rules["min_keyword_weeks"]):
            continue
        per_day = pd.Series(has).groupby(days).sum().reindex(totals.index, fill_value=0)
        share = (per_day / totals).to_numpy()
        fit = trend_fit(share, pd.Series(totals.index), lag)
        rows.append({
            "keyword": keyword, "jobs": int(has.sum()), "weeks_present": weeks_present,
            "mean_share_pct": 100 * share.mean(), "change_pp": 100 * fit["change"],
            "change_low_pp": 100 * fit["change_low"], "change_high_pp": 100 * fit["change_high"],
            "relative_change_pct": fit["relative_change_pct"], "relative_low_pct": fit["relative_low_pct"],
            "relative_high_pct": fit["relative_high_pct"], "p": fit["p"],
            "first_weeks_share_pct": 100 * has[first].mean() if first.any() else np.nan,
            "last_weeks_share_pct": 100 * has[last].mean() if last.any() else np.nan,
        })
    table = pd.DataFrame(rows)
    from ..pay import benjamini_hochberg
    table["p_fdr"] = benjamini_hochberg(table["p"].to_numpy())
    table["week_relative_pct"] = 100 * (table["last_weeks_share_pct"] / table["first_weeks_share_pct"] - 1)
    return table.sort_values("relative_change_pct", ascending=False).reset_index(drop=True)


def new_terms(frame: pd.DataFrame, watch: list[str]) -> pd.DataFrame:
    terms = frame["title_key"].map(title_terms)
    rows = []
    for week, part in terms.groupby(frame["iso_week"]):
        for term in watch:
            rows.append({"iso_week": week, "term": term, "jobs": int(part.map(lambda s: term in s).sum()),
                         "week_jobs": int(len(part))})
    return pd.DataFrame(rows)


def geography(frame: pd.DataFrame, lag: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = frame.assign(region=region_of(frame["country"]))
    weekly_rows = []
    for week, part in frame.groupby("iso_week"):
        hhi, effective = concentration(part["country"])
        weekly_rows.append({"iso_week": week, "jobs": len(part), "days": part["posted_date"].nunique(),
                            "distinct_countries": int(part["country"].nunique()), "hhi": hhi,
                            "effective_countries": effective,
                            "missing_country_pct": 100 * part["country"].isna().mean()})
    weekly = pd.DataFrame(weekly_rows)
    regions = (frame.dropna(subset=["region"]).groupby(["iso_week", "region"]).size().rename("jobs").reset_index())
    regions["share_pct"] = 100 * regions["jobs"] / regions.groupby("iso_week")["jobs"].transform("sum")

    daily_rows = []
    for day, part in frame.groupby("posted_date"):
        hhi, effective = concentration(part["country"])
        known = part["country"].notna()
        daily_rows.append({"date": day, "jobs": len(part), "distinct_countries": int(part["country"].nunique()),
                           "hhi": hhi, "effective_countries": effective,
                           "north_america_share": float((part.loc[known, "region"] == "North America").mean()),
                           "hourly_share": float((part["contract_type"].astype(str) == "hourly").mean())})
    daily = pd.DataFrame(daily_rows)
    return weekly, regions, daily


def signals(frame: pd.DataFrame) -> pd.DataFrame:
    flags = signal_flags(frame["title_key"])
    rows = []
    for week, index in frame.groupby("iso_week").groups.items():
        part = flags.loc[index]
        for name in SIGNALS:
            k, n = int(part[name].sum()), len(part)
            low, high = wilson(k, n)
            rows.append({"iso_week": week, "signal": name, "group": "engagement" if name in ENGAGEMENT_SIGNALS
                         else "work arrangement", "title_mentions": k, "jobs": n, "share_pct": 100 * k / n,
                         "low_pct": 100 * low, "high_pct": 100 * high})
    return pd.DataFrame(rows)


def series_trends(daily: pd.DataFrame, lag: int) -> pd.DataFrame:
    rows = []
    for column, scale, unit in (("hourly_share", 100, "pp"), ("north_america_share", 100, "pp"),
                                ("hhi", 1, "index"), ("effective_countries", 1, "countries")):
        fit = trend_fit(daily[column].to_numpy(), daily["date"], lag)
        rows.append({"series": column, "unit": unit, "mean": scale * daily[column].mean(),
                     "start": scale * fit["start_level"], "end": scale * fit["end_level"],
                     "change": scale * fit["change"], "change_low": scale * fit["change_low"],
                     "change_high": scale * fit["change_high"], "relative_change_pct": fit["relative_change_pct"],
                     "p": fit["p"]})
    return pd.DataFrame(rows)


def run(settings: Settings, context: dict[str, Any]) -> StepRecord:
    record = StepRecord(NAME, DESCRIPTION)
    rules = settings.section("trends")
    lag = int(rules["newey_west_lag"])
    frame = window_jobs(context)
    weeks = complete_weeks(frame["posted_date"])
    processed = settings.path("processed_dir")
    outputs = {}
    if frame["posted_date"].nunique() >= int(rules["min_days"]):
        daily, categories = category_results(frame, lag, weeks)
        outputs["trend_category_daily.csv"] = daily
        outputs["trend_categories.csv"] = categories
        outputs["trend_other_monitor.csv"] = other_monitor(daily, lag)
        outputs["trend_keywords.csv"] = keyword_results(frame, rules, lag, weeks)
        outputs["trend_new_terms_weekly.csv"] = new_terms(frame, list(rules["watch_terms"]))
        weekly, regions, geo_daily = geography(frame, lag)
        outputs["remote_geography_weekly.csv"] = weekly
        outputs["remote_regions_weekly.csv"] = regions
        outputs["remote_daily.csv"] = geo_daily
        outputs["remote_signals_weekly.csv"] = signals(frame)
        outputs["remote_series_trends.csv"] = series_trends(geo_daily, lag)
    else:
        # Too few days to estimate a trend (only in tiny test projects).
        record.metrics["skipped"] = f"fewer than {rules['min_days']} days in the time-series window"
    for name, table in outputs.items():
        path = write_csv(table.round(8), processed / name)
        record.outputs.append(describe_output(path, settings.root, rows=len(table)))
    record.metrics.update({"window_days": int(frame["posted_date"].nunique()), "window_jobs": int(len(frame)),
                           "complete_weeks": ", ".join(weeks)})
    return record
