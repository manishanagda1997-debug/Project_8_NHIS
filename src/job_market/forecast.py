"""Short-horizon forecasting helpers (decision D-033).

Four transparent models, all defined before any evaluation:

* ``seasonal_naive``: each day equals the same weekday one week earlier;
* ``weekday_mean``: each weekday equals its average over the last 14 days;
* ``trend_weekday``: a straight line plus weekday effects (Notebook 05's model),
  continued forward;
* ``damped_trend``: the same line, but the daily trend shrinks by a fixed factor
  ``phi`` each day ahead, so a short-lived change cannot run away.

Errors are measured with MAE, seasonal MASE (scale = in-sample mean absolute
change versus seven days earlier) and Relative MAE (model MAE divided by the
seasonal-naive MAE on the same days; below 1 beats the baseline). MAPE is not
used: small counts make it unstable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MODELS = ("seasonal_naive", "weekday_mean", "trend_weekday", "damped_trend")
SEASON = 7


def _design(t: np.ndarray, weekday: np.ndarray) -> np.ndarray:
    dummies = np.zeros((len(t), 6))
    for d in range(1, 7):
        dummies[:, d - 1] = weekday == d
    return np.column_stack([np.ones_like(t, dtype=float), t.astype(float), dummies])


def forecast_series(history: np.ndarray, start_weekday: int, horizon: int, model: str, phi: float = 0.9,
                    window: int = 14) -> np.ndarray:
    """Forecast ``horizon`` days after ``history`` (one value per day).

    ``start_weekday`` is the weekday (Monday = 0) of ``history[0]``.
    """
    y = np.asarray(history, dtype=float)
    n = len(y)
    future_weekday = (start_weekday + np.arange(n, n + horizon)) % 7
    if model == "seasonal_naive":
        return np.array([y[n - SEASON + (h % SEASON)] for h in range(horizon)])
    if model == "weekday_mean":
        recent = y[-window:]
        recent_weekday = (start_weekday + np.arange(n - len(recent), n)) % 7
        means = {d: recent[recent_weekday == d].mean() for d in range(7)}
        return np.array([means[d] for d in future_weekday])
    t = np.arange(n)
    weekday = (start_weekday + t) % 7
    design = _design(t, weekday)
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    future_t = np.arange(n, n + horizon)
    if model == "trend_weekday":
        return _design(future_t, future_weekday) @ coef
    if model == "damped_trend":
        level_last = _design(np.array([n - 1]), np.array([weekday[-1]])) @ coef
        weekday_effect = np.concatenate([[0.0], coef[2:]])
        base = level_last[0] - weekday_effect[weekday[-1]]          # trend line at the last day, no weekday effect
        steps = np.cumsum(phi ** np.arange(1, horizon + 1))           # damped sum of future trend steps
        return base + coef[1] * steps + weekday_effect[future_weekday]
    raise ValueError(f"unknown model {model}")


def seasonal_scale(history: np.ndarray) -> float:
    """In-sample mean absolute change versus seven days earlier (the MASE scale).

    NaN when it cannot be computed or is zero (a series that never changes
    week on week, such as an empty category): MASE is then undefined.
    """
    y = np.asarray(history, dtype=float)
    if len(y) <= SEASON:
        return np.nan
    scale = float(np.mean(np.abs(y[SEASON:] - y[:-SEASON])))
    return scale if scale > 0 else np.nan


def clip_counts(values: np.ndarray) -> np.ndarray:
    return np.maximum(values, 0.0)


def coherent_shares(share_forecasts: np.ndarray) -> np.ndarray:
    """Clip share forecasts to [0, 1] and rescale every day to sum to 1.

    ``share_forecasts`` has one row per day and one column per category.
    """
    clipped = np.clip(share_forecasts, 0.0, 1.0)
    totals = clipped.sum(axis=1, keepdims=True)
    totals[totals == 0] = 1.0
    return clipped / totals


def coherent_counts(total_forecast: np.ndarray, share_forecasts: np.ndarray) -> np.ndarray:
    """Category counts = total forecast x coherent shares, so categories add up to the total."""
    return clip_counts(total_forecast)[:, None] * coherent_shares(share_forecasts)


def demand_forecast(total: np.ndarray, shares: np.ndarray, start_weekday: int, horizon: int, model: str,
                    phi: float) -> tuple[np.ndarray, np.ndarray]:
    """Coherent demand forecast: total jobs and one column of expected jobs per category."""
    total_f = clip_counts(forecast_series(total, start_weekday, horizon, model, phi))
    share_f = np.column_stack([forecast_series(shares[:, j], start_weekday, horizon, model, phi)
                               for j in range(shares.shape[1])])
    return total_f, coherent_counts(total_f, share_f)


def signal_forecast(values: np.ndarray, start_weekday: int, horizon: int, model: str, phi: float,
                    bounds: tuple[float, float]) -> np.ndarray:
    """Forecast of a bounded signal (a share or a concentration index)."""
    return np.clip(forecast_series(values, start_weekday, horizon, model, phi), bounds[0], bounds[1])


def rolling_origins(n_days: int, first_train: int, horizon: int) -> list[int]:
    """Training lengths for a rolling-origin backtest that stays inside ``n_days``."""
    return list(range(first_train, n_days - horizon + 1))


def error_summary(errors: pd.DataFrame, family: str) -> pd.DataFrame:
    """Average MAE, seasonal MASE and Relative MAE per model.

    ``errors`` has one row per (model, series, origin, horizon) with columns
    ``abs_error``, ``scale`` and ``naive_abs_error``.
    """
    grouped = errors.groupby(["model", "series"])
    per_series = pd.DataFrame({
        "mae": grouped["abs_error"].mean(),
        "mase": grouped.apply(lambda g: (g["abs_error"] / g["scale"]).mean(), include_groups=False),
        "relative_mae": grouped["abs_error"].mean() / grouped["naive_abs_error"].mean(),
    }).reset_index()
    summary = per_series.groupby("model")[["mase", "relative_mae"]].mean().reset_index()
    summary.insert(0, "family", family)
    return summary.sort_values("mase").reset_index(drop=True), per_series


def empirical_ranges(point: np.ndarray, scaled_errors: dict[int, np.ndarray], scale: float, horizon: int,
                     multiplicative: bool, lower: float = 0.1, upper: float = 0.9) -> tuple[np.ndarray, np.ndarray]:
    """80% empirical forecast ranges from backtest errors, wider farther ahead.

    ``scaled_errors[h]`` holds the backtest errors at horizon ``h`` (1..H).
    For multiplicative errors, ``error = actual / forecast - 1``, so
    ``forecast * (1 + error)`` recovers the actual value. For additive errors,
    ``error = (actual - forecast) / scale``, so ``forecast + error * scale``
    recovers the actual value. The ranges are correct only when the errors
    follow these directions. Beyond the backtested horizon H, the horizon-H quantiles are widened by sqrt(h / H) (a fixed
    assumption, stated in the notebook).

    Errors that are not finite (from a series with an undefined seasonal scale)
    are left out of the quantiles; with no finite error the range is undefined.
    For additive ranges, a series whose own scale is undefined gets an undefined
    range.
    """
    tested = max(scaled_errors)
    low, high = np.empty(horizon), np.empty(horizon)
    for h in range(1, horizon + 1):
        base = np.asarray(scaled_errors[min(h, tested)], dtype=float)
        finite = base[np.isfinite(base)]
        widen = np.sqrt(h / tested) if h > tested else 1.0
        if finite.size == 0:
            q_low = q_high = np.nan
        else:
            q_low, q_high = np.quantile(finite, [lower, upper]) * widen
        if multiplicative:
            low[h - 1], high[h - 1] = point[h - 1] * (1 + q_low), point[h - 1] * (1 + q_high)
        else:
            low[h - 1], high[h - 1] = point[h - 1] + q_low * scale, point[h - 1] + q_high * scale
    return low, high
