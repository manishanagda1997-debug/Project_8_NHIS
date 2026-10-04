"""Step 7 - forecast: short-horizon forecasts for Task 3, Task 8 and Task 7.

Decision D-033. Days in the 37-day window are split into a development
period (first 30 days) and a **reserved final forecast evaluation window**
(last 7 days, 17-23 March), which is used neither for fitting nor for model
choice.

Two model families, each with one winner for all its series (no model is
hand-picked per category):

* **demand**: total jobs and the 23 category series (22 functions + Other).
  The forecast is coherent: total jobs and category shares are forecast with
  the same model, shares are clipped and rescaled to sum to 1, and category
  jobs = total x share, so the categories always add up to the total;
* **signals** (Task 7): hourly share, North American client share and the
  concentration index (HHI), each kept inside its valid range.

The winner of a family is the model with the lowest average seasonal MASE
over all its series in a rolling-origin backtest inside the development
period (horizons 1-7). Final forecasts refit the winner on all 37 days and
cover 14 days: days 1-7 are the primary forecast, days 8-14 an extended
outlook with wider, less directly validated ranges.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..config import Settings
from ..forecast import (
    MODELS, demand_forecast, empirical_ranges, error_summary, rolling_origins, seasonal_scale, signal_forecast,
)
from ..io import write_csv
from ..manifest import StepRecord, describe_output
from ..taxonomy import CATEGORY_IDS
from .trends import geography, window_jobs

NAME = "forecast"
DESCRIPTION = "Short-horizon demand forecasts (Tasks 3, 8) and online-hiring signal forecasts (Task 7)."

SIGNALS = {"hourly_share": (0.0, 1.0), "north_america_share": (0.0, 1.0), "hhi": (0.0, 1.0)}


def build_series(context: dict[str, Any]) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, pd.DataFrame]:
    frame = window_jobs(context)
    counts = frame.groupby(["posted_date", "primary_category"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=list(CATEGORY_IDS), fill_value=0).sort_index()
    total = counts.sum(axis=1).to_numpy(dtype=float)
    shares = (counts.to_numpy(dtype=float) / total[:, None])
    _, _, daily = geography(frame, lag=7)
    daily = daily.set_index("date").reindex(counts.index)
    return pd.DatetimeIndex(counts.index), total, shares, daily


def backtest(total: np.ndarray, shares: np.ndarray, signals: pd.DataFrame, start_weekday: int, n_days: int,
             first_train: int, horizon: int, phi: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rolling-origin errors for both families, inside the first ``n_days``."""
    demand_rows, signal_rows = [], []
    counts = total[:, None] * shares
    names = ["total"] + list(CATEGORY_IDS)
    for length in rolling_origins(n_days, first_train, horizon):
        actual_total = total[length:length + horizon]
        actual_counts = counts[length:length + horizon]
        actual = np.column_stack([actual_total, actual_counts])
        forecasts = {}
        for model in MODELS:
            t_f, c_f = demand_forecast(total[:length], shares[:length], start_weekday, horizon, model, phi)
            forecasts[model] = np.column_stack([t_f, c_f])
        history = np.column_stack([total[:length], counts[:length]])
        scales = [seasonal_scale(history[:, j]) for j in range(history.shape[1])]
        for model in MODELS:
            err = np.abs(forecasts[model] - actual)
            naive = np.abs(forecasts["seasonal_naive"] - actual)
            for j, name in enumerate(names):
                for h in range(horizon):
                    demand_rows.append({"model": model, "series": name, "origin": length, "horizon": h + 1,
                                        "abs_error": err[h, j], "naive_abs_error": naive[h, j],
                                        "error": forecasts[model][h, j] - actual[h, j], "scale": scales[j]})
        for name, bounds in SIGNALS.items():
            values = signals[name].to_numpy(dtype=float)
            actual_s = values[length:length + horizon]
            scale = seasonal_scale(values[:length])
            naive_s = signal_forecast(values[:length], start_weekday, horizon, "seasonal_naive", phi, bounds)
            for model in MODELS:
                f = signal_forecast(values[:length], start_weekday, horizon, model, phi, bounds)
                for h in range(horizon):
                    signal_rows.append({"model": model, "series": name, "origin": length, "horizon": h + 1,
                                        "abs_error": abs(f[h] - actual_s[h]), "naive_abs_error": abs(naive_s[h] - actual_s[h]),
                                        "error": f[h] - actual_s[h], "scale": scale})
    return pd.DataFrame(demand_rows), pd.DataFrame(signal_rows)


def final_evaluation(total, shares, signals, start_weekday, dev_days, final_days, phi) -> pd.DataFrame:
    """Fit on the development period only and score the reserved final window."""
    rows = []
    counts = total[:, None] * shares
    names = ["total"] + list(CATEGORY_IDS)
    actual = np.column_stack([total, counts])[dev_days:dev_days + final_days]
    history = np.column_stack([total[:dev_days], counts[:dev_days]])
    preds = {}
    for model in MODELS:
        t_f, c_f = demand_forecast(total[:dev_days], shares[:dev_days], start_weekday, final_days, model, phi)
        preds[model] = np.column_stack([t_f, c_f])
    for model in MODELS:
        for j, name in enumerate(names):
            mae = float(np.mean(np.abs(preds[model][:, j] - actual[:, j])))
            naive = float(np.mean(np.abs(preds["seasonal_naive"][:, j] - actual[:, j])))
            rows.append({"family": "demand", "model": model, "series": name, "mae": mae,
                         "mase": mae / seasonal_scale(history[:, j]), "relative_mae": mae / naive if naive else np.nan})
    for name, bounds in SIGNALS.items():
        values = signals[name].to_numpy(dtype=float)
        actual_s = values[dev_days:dev_days + final_days]
        naive_f = signal_forecast(values[:dev_days], start_weekday, final_days, "seasonal_naive", phi, bounds)
        naive = float(np.mean(np.abs(naive_f - actual_s)))
        for model in MODELS:
            f = signal_forecast(values[:dev_days], start_weekday, final_days, model, phi, bounds)
            mae = float(np.mean(np.abs(f - actual_s)))
            rows.append({"family": "signals", "model": model, "series": name, "mae": mae,
                         "mase": mae / seasonal_scale(values[:dev_days]), "relative_mae": mae / naive if naive else np.nan})
    return pd.DataFrame(rows)


def standardized_errors(errors: pd.DataFrame, model: str) -> dict[int, np.ndarray]:
    part = errors[errors["model"] == model]
    return {int(h): (g["error"] / g["scale"]).to_numpy() for h, g in part.groupby("horizon")}


def run(settings: Settings, context: dict[str, Any]) -> StepRecord:
    record = StepRecord(NAME, DESCRIPTION)
    rules = settings.section("forecast")
    phi = float(rules["damping_phi"])
    tested, horizon = int(rules["tested_horizon_days"]), int(rules["horizon_days"])
    final_days, first_train = int(rules["final_days"]), int(rules["first_train_days"])
    days, total, shares, signals = build_series(context)
    n = len(days)
    dev_days = n - final_days
    if dev_days < first_train + tested:
        record.metrics["forecast_skipped"] = f"only {n} days; at least {first_train + tested + final_days} needed"
        return record
    start_weekday = int(days[0].dayofweek)

    # 1. Model choice inside the development period only.
    demand_err, signal_err = backtest(total[:dev_days], shares[:dev_days], signals.iloc[:dev_days], start_weekday,
                                      dev_days, first_train, tested, phi)
    demand_summary, demand_per_series = error_summary(demand_err, "demand")
    signal_summary, signal_per_series = error_summary(signal_err, "signals")
    choice = pd.concat([demand_summary, signal_summary], ignore_index=True)
    winners = {family: table.iloc[0]["model"] for family, table in (("demand", demand_summary), ("signals", signal_summary))}
    choice["chosen"] = [winners[f] == m for f, m in zip(choice["family"], choice["model"])]
    per_series = pd.concat([demand_per_series.assign(family="demand"), signal_per_series.assign(family="signals")])

    # Secondary check: the few 14-day backtests that fit inside the development period.
    d14, s14 = backtest(total[:dev_days], shares[:dev_days], signals.iloc[:dev_days], start_weekday, dev_days,
                        first_train, horizon, phi)
    long_rows = []
    for family, err in (("demand", d14), ("signals", s14)):
        late = err[err["horizon"] > tested]
        if late.empty:
            continue
        summary, _ = error_summary(late, family)
        summary["origins"] = int(late["origin"].nunique())
        long_rows.append(summary)
    long_check = pd.concat(long_rows, ignore_index=True) if long_rows else pd.DataFrame()

    # 2. Reserved final window, scored once with the models as defined.
    final = final_evaluation(total, shares, signals, start_weekday, dev_days, final_days, phi)
    final["chosen"] = [winners[f] == m for f, m in zip(final["family"], final["model"])]

    # 3. Final 14-day forecasts from the winners, refitted on all days.
    future = pd.date_range(days[-1] + pd.Timedelta(days=1), periods=horizon, freq="D")
    t_f, c_f = demand_forecast(total, shares, start_weekday, horizon, winners["demand"], phi)
    demand_std = standardized_errors(demand_err, winners["demand"])
    counts = total[:, None] * shares
    names = ["total"] + list(CATEGORY_IDS)
    points = np.column_stack([t_f, c_f])
    history = np.column_stack([total, counts])
    daily_rows = []
    for j, name in enumerate(names):
        low, high = empirical_ranges(points[:, j], demand_std, seasonal_scale(history[:, j]), horizon, False,
                                     float(rules["range_lower"]), float(rules["range_upper"]))
        low = np.maximum(low, 0.0)
        for h in range(horizon):
            daily_rows.append({"date": future[h].strftime("%Y-%m-%d"), "horizon": h + 1, "series": name,
                               "forecast": points[h, j], "low": low[h], "high": high[h],
                               "share": points[h, j] / t_f[h] if name != "total" and t_f[h] else np.nan})
    demand_daily = pd.DataFrame(daily_rows)

    recent = slice(n - 7, n)
    # Task 8 direction: taken from the better trend-style model for each series,
    # and reported only when that model beat the seasonal baseline in the backtest.
    trend_models = ("trend_weekday", "damped_trend")
    trend_shares = {}
    for model in trend_models:
        t_m, c_m = demand_forecast(total, shares, start_weekday, horizon, model, phi)
        trend_shares[model] = c_m / np.where(t_m[:, None] > 0, t_m[:, None], 1.0)
    rel = demand_per_series.pivot(index="series", columns="model", values="relative_mae")
    stable = float(rules["stable_change_pp"])
    summary_rows = []
    for name in names:
        part = demand_daily[demand_daily["series"] == name]
        first, second = part[part["horizon"] <= tested], part[part["horizon"] > tested]
        row = {"series": name,
               "recent_jobs_per_day": float(history[recent, names.index(name)].mean()),
               "forecast_jobs_per_day_1_7": first["forecast"].mean(), "low_1_7": first["low"].mean(),
               "high_1_7": first["high"].mean(), "forecast_jobs_per_day_8_14": second["forecast"].mean(),
               "low_8_14": second["low"].mean(), "high_8_14": second["high"].mean()}
        if name != "total":
            row["recent_share_pct"] = 100 * float(shares[recent, CATEGORY_IDS.index(name)].mean())
            row["forecast_share_pct_1_7"] = 100 * first["share"].mean()
            row["forecast_share_pct_1_14"] = 100 * part["share"].mean()
            best_model = min(trend_models, key=lambda m: rel.loc[name, m])
            best_trend = float(rel.loc[name, best_model])
            row["trend_model"] = best_model
            row["trend_model_relative_mae"] = best_trend
            row["trend_share_pct_1_14"] = 100 * float(trend_shares[best_model][:, CATEGORY_IDS.index(name)].mean())
            change = row["trend_share_pct_1_14"] - row["recent_share_pct"]
            row["trend_change_pp"] = change
            if best_trend >= 1:
                row["direction"] = "no reliable direction"
            elif abs(change) < stable:
                row["direction"] = "stable"
            else:
                row["direction"] = "rising" if change > 0 else "falling"
        summary_rows.append(row)
    demand_outlook = pd.DataFrame(summary_rows)
    ranked = demand_outlook[demand_outlook["series"] != "total"].sort_values("forecast_jobs_per_day_1_7", ascending=False)
    demand_outlook["rank_1_7"] = demand_outlook["series"].map({s: i + 1 for i, s in enumerate(ranked["series"])})

    signal_std = standardized_errors(signal_err, winners["signals"])
    signal_rows, signal_summary_rows = [], []
    signal_rel = signal_per_series.pivot(index="series", columns="model", values="relative_mae")
    for name, bounds in SIGNALS.items():
        values = signals[name].to_numpy(dtype=float)
        f = signal_forecast(values, start_weekday, horizon, winners["signals"], phi, bounds)
        low, high = empirical_ranges(f, signal_std, seasonal_scale(values), horizon, False,
                                     float(rules["range_lower"]), float(rules["range_upper"]))
        low, high = np.clip(low, *bounds), np.clip(high, *bounds)
        for h in range(horizon):
            signal_rows.append({"date": future[h].strftime("%Y-%m-%d"), "horizon": h + 1, "series": name,
                                "forecast": f[h], "low": low[h], "high": high[h]})
        best_model = min(trend_models, key=lambda m: signal_rel.loc[name, m])
        best_trend = float(signal_rel.loc[name, best_model])
        recent_value = float(values[recent].mean())
        trend_f = signal_forecast(values, start_weekday, horizon, best_model, phi, bounds)
        change = float(trend_f.mean() - recent_value)
        threshold = stable / 100 if name != "hhi" else 0.001
        direction = ("no reliable direction" if best_trend >= 1 else "stable" if abs(change) < threshold
                     else "rising" if change > 0 else "falling")
        signal_summary_rows.append({"series": name, "recent_value": recent_value, "forecast_1_7": f[:tested].mean(),
                                    "forecast_1_14": f.mean(), "trend_model": best_model,
                                    "trend_model_relative_mae": best_trend, "trend_forecast_1_14": float(trend_f.mean()),
                                    "direction": direction})

    processed = settings.path("processed_dir")
    for name, table in (
        ("forecast_model_choice.csv", choice),
        ("forecast_backtest_by_series.csv", per_series[["family", "model", "series", "mae", "mase", "relative_mae"]]),
        ("forecast_backtest_14d.csv", long_check),
        ("forecast_final_evaluation.csv", final),
        ("forecast_demand_daily.csv", demand_daily),
        ("forecast_demand_outlook.csv", demand_outlook),
        ("forecast_signals_daily.csv", pd.DataFrame(signal_rows)),
        ("forecast_signals_outlook.csv", pd.DataFrame(signal_summary_rows)),
    ):
        path = write_csv(table.round(6), processed / name)
        record.outputs.append(describe_output(path, settings.root, rows=len(table)))
    record.metrics = {"forecast_development_days": dev_days, "forecast_final_days": final_days,
                      "demand_model": winners["demand"], "signals_model": winners["signals"],
                      "first_forecast_day": future[0].strftime("%Y-%m-%d"),
                      "last_forecast_day": future[-1].strftime("%Y-%m-%d")}
    return record
