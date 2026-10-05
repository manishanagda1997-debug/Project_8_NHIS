"""Short-horizon forecasting (decision D-033)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from job_market.forecast import (
    MODELS, coherent_counts, coherent_shares, demand_forecast, empirical_ranges, error_summary, forecast_series,
    rolling_origins, seasonal_scale, signal_forecast,
)

WEEK = np.array([10.0, 12, 11, 13, 9, 5, 4])


def test_seasonal_naive_repeats_last_week():
    history = np.tile(WEEK, 3)
    assert forecast_series(history, 0, 10, "seasonal_naive").tolist() == np.tile(WEEK, 2)[:10].tolist()


def test_weekday_mean_uses_the_last_two_weeks():
    history = np.concatenate([np.tile(WEEK + 100, 2), np.tile(WEEK, 2)])   # old weeks are ignored
    assert np.allclose(forecast_series(history, 0, 7, "weekday_mean"), WEEK)


def test_trend_weekday_continues_a_line():
    t = np.arange(28)
    history = 50 + 0.5 * t + np.tile(WEEK, 4)
    future = 50 + 0.5 * np.arange(28, 35) + WEEK
    assert np.allclose(forecast_series(history, 0, 7, "trend_weekday"), future)


def test_damped_trend_grows_less_than_the_straight_line():
    t = np.arange(28)
    history = 50 + 0.5 * t + np.tile(WEEK, 4)
    straight = forecast_series(history, 0, 14, "trend_weekday")
    damped = forecast_series(history, 0, 14, "damped_trend", phi=0.9)
    assert damped[0] == pytest.approx(straight[0] - 0.5 * (1 - 0.9), abs=1e-9)
    assert (np.diff(damped - straight) < 0).all()                 # the gap widens: the trend fades
    flat = forecast_series(np.tile(WEEK, 4), 0, 7, "damped_trend")
    assert np.allclose(flat, WEEK)                                 # no trend, no drift


def test_unknown_model_fails():
    with pytest.raises(ValueError):
        forecast_series(np.ones(14), 0, 7, "magic")


def test_coherent_shares_and_counts_add_up():
    raw = np.array([[0.5, 0.6, -0.1], [0.2, 0.2, 0.2]])
    shares = coherent_shares(raw)
    assert np.allclose(shares.sum(axis=1), 1.0)
    assert (shares >= 0).all()
    counts = coherent_counts(np.array([100.0, -5.0]), raw)
    assert np.allclose(counts.sum(axis=1), [100.0, 0.0])          # negative totals are clipped to 0


def test_demand_forecast_categories_sum_to_total():
    rng = np.random.default_rng(0)
    total = 6000 + np.tile(WEEK * 50, 4)
    shares = rng.dirichlet(np.ones(5), size=28)
    for model in MODELS:
        t_f, c_f = demand_forecast(total, shares, 4, 14, model, 0.9)
        assert np.allclose(c_f.sum(axis=1), t_f)
        assert (c_f >= 0).all()


def test_signal_forecast_respects_bounds():
    history = np.linspace(0.05, 0.95, 28)
    assert signal_forecast(history, 0, 30, "trend_weekday", 0.9, (0.0, 1.0)).max() <= 1.0


def test_seasonal_scale_and_origins():
    assert np.isnan(seasonal_scale(np.tile(WEEK, 3)))              # no week-on-week change: MASE undefined
    assert seasonal_scale(np.arange(14.0)) == 7.0
    assert rolling_origins(30, 14, 7) == list(range(14, 24))


def test_error_summary_relative_mae():
    errors = pd.DataFrame({
        "model": ["a", "a", "seasonal_naive", "seasonal_naive"], "series": ["x", "x", "x", "x"],
        "abs_error": [1.0, 3.0, 2.0, 2.0], "naive_abs_error": [2.0, 2.0, 2.0, 2.0], "scale": [2.0] * 4,
    })
    summary, per_series = error_summary(errors, "demand")
    row = per_series.set_index("model").loc["a"]
    assert row["mae"] == 2.0 and row["relative_mae"] == 1.0 and row["mase"] == 1.0


def test_empirical_ranges_widen_beyond_the_tested_horizon():
    errors = {h: np.linspace(-1, 1, 101) * h for h in range(1, 8)}
    low, high = empirical_ranges(np.full(14, 100.0), errors, scale=10.0, horizon=14, multiplicative=False)
    width = high - low
    assert (np.diff(width[:7]) > 0).all()                          # wider farther ahead
    assert width[13] == pytest.approx(width[6] * np.sqrt(14 / 7))
    assert (low < 100).all() and (high > 100).all()
