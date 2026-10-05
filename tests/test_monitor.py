"""Monthly and weekly monitoring tables (decision D-036)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from job_market.monitor import group_shares, hhi_effective, monthly_summary, prepare, weekday_standardized, weekly_summary


def frame_for(days: pd.DatetimeIndex, per_day) -> pd.DataFrame:
    rows = []
    for day in days:
        n = per_day(day)
        for i in range(n):
            rows.append({"row_id": len(rows) + 1, "posted_date": day, "iso_week": f"{day.isocalendar().year}-W{day.isocalendar().week:02d}",
                         "contract_type": "hourly" if i % 2 == 0 else "fixed",
                         "country": ["United States", "India", None][i % 3],
                         "hourly_mid": 20.0 + i if i % 2 == 0 else np.nan,
                         "eligible_for_hourly_rate_analysis": i % 2 == 0,
                         "primary_category": ["web_development", "design_creative"][i % 2]})
    return prepare(pd.DataFrame(rows))


def test_weekday_standardized_removes_weekday_mix():
    # Weekends have 10 jobs, weekdays 20. A window with extra weekend days has a lower plain
    # average, but the same weekday-standardized value.
    def per_day(day):
        return 10 if day.dayofweek >= 5 else 20
    two_weeks = pd.date_range("2024-02-19", periods=14)
    extra_weekends = pd.date_range("2024-02-19", periods=14).append(pd.DatetimeIndex(["2024-03-09", "2024-03-10"]))
    a = pd.DataFrame({"date": two_weeks, "jobs": [per_day(d) for d in two_weeks]})
    b = pd.DataFrame({"date": extra_weekends, "jobs": [per_day(d) for d in extra_weekends]})
    assert b["jobs"].mean() < a["jobs"].mean()
    assert weekday_standardized(a) == pytest.approx(weekday_standardized(b))
    assert np.isnan(weekday_standardized(a.iloc[:5]))                     # a weekday is missing


def test_effective_countries_ignores_missing_and_volume():
    assert hhi_effective(pd.Series(["A", "B", None, None])) == (0.5, 2.0)
    assert hhi_effective(pd.Series(["A", "B"] * 50))[1] == pytest.approx(2.0)   # more jobs, same spread
    assert np.isnan(hhi_effective(pd.Series([None, None]))[1])


def test_partial_months_are_labelled_and_new_months_appear():
    days = pd.date_range("2024-02-16", "2024-04-30")
    frame = frame_for(days, lambda d: 6)
    months = monthly_summary(frame)
    assert months["month"].tolist() == ["2024-02", "2024-03", "2024-04"]       # nothing names a month
    assert months["label"].tolist() == ["Feb 2024 (14 days)", "Mar 2024", "Apr 2024"]
    assert months["partial"].tolist() == [True, False, False]
    assert months["jobs_per_day"].tolist() == [6.0, 6.0, 6.0]
    assert months.loc[0, "median_hourly_rate"] == pytest.approx(22.0)         # mids 20, 22, 24
    assert months.loc[0, "known_country_pct"] == pytest.approx(100 * 4 / 6)


def test_weekly_summary_marks_partial_weeks():
    frame = frame_for(pd.date_range("2024-02-16", "2024-03-03"), lambda d: 3)
    weeks = weekly_summary(frame)
    assert weeks["iso_week"].tolist() == ["2024-W07", "2024-W08", "2024-W09"]
    assert weeks["complete"].tolist() == [False, True, True]
    assert weeks["week_start"].tolist() == ["2024-02-12", "2024-02-19", "2024-02-26"]


def test_group_shares_sum_to_100_and_skip_missing_countries():
    frame = frame_for(pd.date_range("2024-03-01", periods=3), lambda d: 6)
    cats = group_shares(frame, "month", "primary_category")
    assert cats.groupby("month")["share_pct"].sum().round(6).eq(100).all()
    countries = group_shares(frame, "month", "country", known_only=True)
    assert set(countries["country"]) == {"United States", "India"}
    assert countries["share_pct"].tolist() == [50.0, 50.0]
