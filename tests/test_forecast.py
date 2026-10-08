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


# --- Forecast ranges must follow the residual direction (actual - forecast). ---
# These tests run the published chain: backtest -> standardized_errors -> bounds.
# A trending series makes the weekday-mean model miss in one direction only, so
# the residuals are one-signed and a mirrored range would sit on the wrong side.

from job_market.steps.forecast import (  # noqa: E402
    SIGNALS, backtest, demand_bounds, signal_bounds, standardized_errors,
)
from job_market.taxonomy import CATEGORY_IDS  # noqa: E402

RULES = {"range_lower": 0.1, "range_upper": 0.9}
DAYS, FIRST_TRAIN, H = 35, 14, 7


def trending_inputs(direction: int):
    t = np.arange(DAYS, dtype=float)
    pattern = np.tile([1.0, 1.05, 1.02, 1.04, 0.97, 0.7, 0.68], DAYS // 7)
    total = (3000 + direction * 25 * t) * pattern
    # Constant shares: every demand series moves with the total, so the pooled
    # demand residuals (one pool per family) all have the same sign.
    weights = np.linspace(1.0, 2.0, len(CATEGORY_IDS))
    shares = np.tile(weights / weights.sum(), (DAYS, 1))
    signal = 0.5 + direction * 0.005 * t
    signals = pd.DataFrame({name: signal for name in SIGNALS})
    return total, shares, signals


def published_ranges(direction: int):
    total, shares, signals = trending_inputs(direction)
    demand_err, signal_err = backtest(total, shares, signals, 0, DAYS, FIRST_TRAIN, H, 0.9)
    t_f, c_f = demand_forecast(total, shares, 0, H, "weekday_mean", 0.9)
    points = np.column_stack([t_f, c_f])
    history = np.column_stack([total, total[:, None] * shares])
    low, high = demand_bounds(points, standardized_errors(demand_err, "weekday_mean"), history, H, RULES)
    values = signals["hourly_share"].to_numpy()
    s_point = signal_forecast(values, 0, H, "weekday_mean", 0.9, SIGNALS["hourly_share"])
    s_low, s_high = signal_bounds(s_point, standardized_errors(signal_err, "weekday_mean"), values, H, RULES,
                                  SIGNALS["hourly_share"])
    return points, low, high, s_point, s_low, s_high


def test_rising_series_get_ranges_above_the_forecast():
    points, low, high, s_point, s_low, s_high = published_ranges(+1)
    assert (low[:, 0] > points[:, 0]).all()                   # total demand is under-forecast
    assert (low[:, 1] > points[:, 1]).all()                   # and a category that rises with it
    assert (s_low > s_point).all()                            # and the rising signal


def test_falling_series_get_ranges_below_the_forecast():
    points, low, high, s_point, s_low, s_high = published_ranges(-1)
    assert (high[:, 0] < points[:, 0]).all()
    assert (high[:, 1] < points[:, 1]).all()
    assert (s_high < s_point).all()


def test_backtest_stores_actual_minus_forecast():
    total, shares, signals = trending_inputs(+1)
    demand_err, signal_err = backtest(total, shares, signals, 0, DAYS, FIRST_TRAIN, H, 0.9)
    row = demand_err[(demand_err["model"] == "seasonal_naive") & (demand_err["series"] == "total")
                     & (demand_err["origin"] == FIRST_TRAIN) & (demand_err["horizon"] == 1)].iloc[0]
    assert row["error"] == pytest.approx(total[FIRST_TRAIN] - total[FIRST_TRAIN - 7])
    srow = signal_err[(signal_err["model"] == "seasonal_naive") & (signal_err["series"] == "hourly_share")
                      & (signal_err["origin"] == FIRST_TRAIN) & (signal_err["horizon"] == 1)].iloc[0]
    values = signals["hourly_share"].to_numpy()
    assert srow["error"] == pytest.approx(values[FIRST_TRAIN] - values[FIRST_TRAIN - 7])


# --- Reserved-window coverage (built from the development period only). ---

from job_market.steps.forecast import coverage_row, final_coverage, final_window_bounds  # noqa: E402

DEV, FINAL = 28, 7


def window_bounds(total, shares, signals):
    demand_err, signal_err = backtest(total[:DEV], shares[:DEV], signals.iloc[:DEV], 0, DEV, FIRST_TRAIN, H, 0.9)
    winners = {"demand": "weekday_mean", "signals": "weekday_mean"}
    bounds = final_window_bounds(total, shares, signals, 0, DEV, FINAL, 0.9, winners,
                                 standardized_errors(demand_err, "weekday_mean"),
                                 standardized_errors(signal_err, "weekday_mean"), RULES)
    return bounds, winners


def test_final_window_ranges_ignore_the_final_window():
    total, shares, signals = trending_inputs(+1)
    changed_total, changed_signals = total.copy(), signals.copy()
    changed_total[DEV:] *= 3                                   # the reserved week changes a lot ...
    changed_signals.iloc[DEV:] = 0.05
    before, _ = window_bounds(total, shares, signals)
    after, _ = window_bounds(changed_total, shares, changed_signals)
    for name in before:                                        # ... but no range may move
        for a, b in zip(before[name], after[name]):
            assert np.array_equal(a, b), name


def test_coverage_counts_undefined_bounds_separately():
    actual = np.array([1.0, 2, 3, 4, 5, 6, 7])
    low = np.array([0.0, 0, 0, np.nan, 10, 0, np.nan])
    high = np.array([9.0, 9, 9, 9, 20, 9, 9])
    row = coverage_row("demand", "m", "s", actual, low, high, "jobs per day", 1.0)
    assert (row["expected"], row["valid"], row["undefined"], row["inside"]) == (7, 5, 2, 4)
    assert row["coverage"] == pytest.approx(4 / 5)
    none = coverage_row("demand", "m", "s", actual, np.full(7, np.nan), high, "jobs per day", 1.0)
    assert none["valid"] == 0 and np.isnan(none["coverage"]) and np.isnan(none["relative_width"])
    zero = coverage_row("demand", "m", "s", np.zeros(7), np.zeros(7), np.ones(7), "jobs per day", 1.0)
    assert np.isnan(zero["relative_width"]) and zero["coverage"] == 1.0


def test_coverage_table_has_every_series_and_pooled_rows():
    total, shares, signals = trending_inputs(+1)
    bounds, winners = window_bounds(total, shares, signals)
    table = final_coverage(bounds, total, shares, signals, DEV, FINAL, winners)
    demand = table[(table["family"] == "demand") & (table["series"] != "pooled")]
    assert len(demand) == 1 + len(CATEGORY_IDS) and demand["expected"].eq(FINAL).all()
    pooled = table[table["series"] == "pooled"].set_index("family")
    assert pooled.loc["demand", "expected"] == FINAL * (1 + len(CATEGORY_IDS))
    assert pooled.loc["signals", "expected"] == FINAL * len(SIGNALS)
    signal_units = table[table["family"] == "signals"].set_index("series")["width_unit"]
    assert signal_units["hhi"] == "index units" and signal_units["hourly_share"] == "percentage points"
