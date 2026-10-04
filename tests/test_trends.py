"""Short-window trends and online-hiring signals (decision D-032)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from job_market.trends import (
    COUNTRY_REGION, UNMAPPED_REGION, complete_weeks, concentration, daily_shares, newey_west_cov, region_of,
    signal_flags, trend_fit, trend_table, week_comparison, wilson,
)

DATES = pd.Series(pd.date_range("2024-02-16", "2024-03-23", freq="D"))


def test_trend_fit_recovers_slope_with_weekday_effects():
    t = np.arange(len(DATES))
    weekday = np.array([0.0, 0.01, 0.02, 0.01, 0.0, -0.02, -0.03])[DATES.dt.dayofweek]
    values = 0.10 + 0.001 * t + weekday
    fit = trend_fit(values, DATES, lag=7)
    assert fit["change"] == pytest.approx(0.001 * (len(DATES) - 1), abs=1e-9)
    assert fit["relative_change_pct"] == pytest.approx(100 * fit["change"] / fit["start_level"])
    assert fit["change_low"] <= fit["change"] <= fit["change_high"]


def test_no_trend_is_not_significant():
    rng = np.random.default_rng(0)
    fit = trend_fit(0.05 + rng.normal(0, 0.002, len(DATES)), DATES, lag=7)
    assert fit["change_low"] < 0 < fit["change_high"]


def test_newey_west_with_lag_zero_is_the_robust_sandwich():
    rng = np.random.default_rng(1)
    design = np.column_stack([np.ones(50), rng.normal(size=50)])
    residuals = rng.normal(size=50)
    bread = np.linalg.inv(design.T @ design)
    expected = bread @ (design.T * residuals**2) @ design @ bread
    assert np.allclose(newey_west_cov(design, residuals, 0), expected)


def test_complete_weeks_in_the_real_window():
    assert complete_weeks(DATES) == ["2024-W08", "2024-W09", "2024-W10", "2024-W11"]


def frame():
    rows = []
    for day in DATES:
        n_a = 30 + (day - DATES.min()).days       # category "a" grows
        rows += [{"posted_date": day, "cat": "a"}] * n_a + [{"posted_date": day, "cat": "b"}] * 60
    out = pd.DataFrame(rows)
    iso = out["posted_date"].dt.isocalendar()
    out["iso_week"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    return out


def test_daily_shares_sum_to_one_and_trend_direction():
    shares = daily_shares(frame(), "cat")
    assert np.allclose(shares.groupby("date")["share"].sum(), 1.0)
    table = trend_table(shares, "cat", lag=7).set_index("cat")
    assert table.loc["a", "change_pp"] > 0 > table.loc["b", "change_pp"]
    assert table.loc["a", "change_pp"] == pytest.approx(-table.loc["b", "change_pp"])
    assert "p_fdr" in table.columns


def test_week_comparison_uses_first_and_last_two_complete_weeks():
    table = week_comparison(frame(), "cat", complete_weeks(DATES)).set_index("cat")
    assert table.loc["a", "last_weeks_share_pct"] > table.loc["a", "first_weeks_share_pct"]
    assert table["first_weeks_share_pct"].sum() == pytest.approx(100.0)


def test_concentration_and_effective_number():
    hhi, effective = concentration(pd.Series(["US", "UK", None, "US", "UK"]))
    assert hhi == pytest.approx(0.5)
    assert effective == pytest.approx(2.0)


def test_regions_keep_missing_missing():
    regions = region_of(pd.Series(["India", "Atlantis", None]))
    assert regions.tolist()[:2] == ["South Asia", UNMAPPED_REGION] and pd.isna(regions.iloc[2])
    assert COUNTRY_REGION["United States"] == "North America"


def test_signals_match_whole_words_only():
    flags = signal_flags(pd.Series(["local seo expert", "must be local in person", "best logo",
                                    "remote assistant est time zone", "hybrid role"]))
    assert flags["on-site / in person / local"].tolist() == [False, True, False, False, False]
    assert flags["time-zone requirement"].tolist() == [False, False, False, True, False]   # "best" is not "est"
    assert flags["remote"].tolist() == [False, False, False, True, False]
    assert flags["hybrid"].tolist() == [False, False, False, False, True]


def test_wilson_bounds():
    low, high = wilson(5, 1000)
    assert 0 <= low < 0.005 < high <= 1
