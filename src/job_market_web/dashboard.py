"""Market dashboard (Task 6, decision D-036): reads verified pipeline tables and draws them.

This module computes nothing new. Every number comes from a table written by
the pipeline (the monitor, trends, pay and forecast steps); here the tables
are only arranged into Plotly figure specifications (plain dictionaries that
the browser draws with the locally served plotly.js). A table that a build
does not have shows "not available in this build" instead of failing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from job_market.config import Settings
from job_market.manifest import verify_output
from job_market.taxonomy import CATEGORIES

REQUIRED = ("monthly_market_summary.csv", "monthly_category_share.csv", "monthly_country_share.csv",
            "weekly_market_summary.csv", "weekly_category_share.csv")
OPTIONAL = ("trend_categories.csv", "pay_keywords_hourly.csv", "pay_countries.csv", "forecast_demand_daily.csv",
            "forecast_demand_outlook.csv", "forecast_signals_daily.csv", "forecast_signals_outlook.csv",
            "remote_daily.csv")

BLUE, ORANGE, AQUA, RED, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#b8b6b0"
LIGHT_BLUE, LIGHT_ORANGE = "#b7d3f6", "rgba(235,104,52,0.16)"
SERIES = (BLUE, ORANGE, AQUA)
INK, MUTED, GRID = "#17181a", "#5d6066", "#ecebe7"
SEQUENTIAL = [[0.0, "#cde2fb"], [0.25, "#86b6ef"], [0.5, "#3987e5"], [0.75, "#1c5cab"], [1.0, "#0d366b"]]
NAMES = {key: name for key, (name, _) in CATEGORIES.items()}


class DashboardError(RuntimeError):
    pass


@dataclass
class DashboardData:
    build_id: str
    tables: dict[str, pd.DataFrame | None] = field(default_factory=dict)

    def get(self, name: str) -> pd.DataFrame | None:
        table = self.tables.get(name)
        return None if table is None or table.empty else table


def load_dashboard(settings: Settings, manifest: dict) -> DashboardData:
    """Read the dashboard tables of the build, verifying each file's recorded SHA-256."""
    entries = {entry["path"]: entry for entry in manifest["outputs"]}
    tables: dict[str, pd.DataFrame | None] = {}
    for name in REQUIRED + OPTIONAL:
        entry = entries.get(settings.relative(settings.path("processed_dir") / name))
        if entry is None:
            if name in REQUIRED:
                raise DashboardError(f"{name} is not an output of build {manifest['run_id']}. "
                                     "Run: python -m job_market rebuild")
            tables[name] = None
            continue
        path = verify_output(entry, settings.root)
        try:
            tables[name] = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            tables[name] = None
    return DashboardData(build_id=manifest["run_id"], tables=tables)


# ----------------------------------------------------------------- helpers


def layout(**extra: Any) -> dict:
    base = {
        "font": {"family": "system-ui, -apple-system, Segoe UI, Roboto, sans-serif", "size": 12, "color": INK},
        "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
        "margin": {"l": 56, "r": 16, "t": 12, "b": 44}, "hovermode": "closest",
        "xaxis": {"gridcolor": GRID, "linecolor": "#cfccc5", "zeroline": False},
        "yaxis": {"gridcolor": GRID, "linecolor": "#cfccc5", "zeroline": False},
        "legend": {"orientation": "h", "y": -0.18, "x": 0, "font": {"color": MUTED}},
        "hoverlabel": {"bgcolor": "#ffffff", "bordercolor": "#cfccc5", "font": {"color": INK}},
    }
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def name_of(category: str) -> str:
    return NAMES.get(category, category.replace("_", " ").title())


def week_label(row) -> str:
    start = pd.Timestamp(row.week_start)
    return f"{row.iso_week[-3:]}<br>{start:%d %b}"


def money(value: float) -> str:
    return "n/a" if pd.isna(value) else (f"${value:,.0f}" if float(value).is_integer() else f"${value:,.2f}")


# --------------------------------------------------------------- headlines


def headline_tiles(data: DashboardData) -> list[dict]:
    """The headline numbers per observed month, with the descriptive change between the last two."""
    months = data.get("monthly_market_summary.csv")
    rows = list(months.itertuples()) if months is not None else []
    if not rows:
        return []
    last = rows[-1]
    prev = rows[-2] if len(rows) > 1 else None

    def tile(title, values, change, note):
        return {"title": title, "cells": values, "change": change, "note": note}

    def per_month(fmt):
        return [{"label": r.label, "value": fmt(r)} for r in rows[-3:]]

    def pct_change(a, b):
        return None if prev is None or pd.isna(a) or pd.isna(b) or a == 0 else f"{(b / a - 1) * 100:+.1f}%"

    def diff(a, b, fmt):
        return None if prev is None or pd.isna(a) or pd.isna(b) else fmt(b - a)

    std_note = "Average of the seven weekday means, so a month with more Fridays or Saturdays is not favoured."
    tiles = [
        tile("Jobs per day (weekday-standardized)",
             per_month(lambda r: "n/a" if pd.isna(r.jobs_per_day_weekday_std) else f"{r.jobs_per_day_weekday_std:,.0f}"),
             pct_change(prev.jobs_per_day_weekday_std, last.jobs_per_day_weekday_std) if prev is not None else None,
             std_note + " Plain daily average: " + ", ".join(f"{r.label}: {r.jobs_per_day:,.0f}" for r in rows[-3:]) + "."),
        tile("Hourly jobs", per_month(lambda r: f"{r.hourly_share_pct:.1f}%"),
             diff(prev.hourly_share_pct, last.hourly_share_pct, lambda d: f"{d:+.1f} pp") if prev is not None else None,
             "Share of all jobs in the period that are hourly (the rest are fixed-price)."),
        tile("Median hourly rate", per_month(lambda r: money(r.median_hourly_rate)),
             diff(prev.median_hourly_rate, last.median_hourly_rate, lambda d: ("+" if d >= 0 else "-") + money(abs(d))) if prev is not None else None,
             "Midpoint of complete stated hourly ranges, jobs eligible for hourly-rate analysis (Notebook 04)."),
        tile("Effective number of client countries", per_month(lambda r: f"{r.effective_countries:.2f}"),
             diff(prev.effective_countries, last.effective_countries, lambda d: f"{d:+.2f}") if prev is not None else None,
             "1 / concentration (HHI) of known client countries: the jobs are spread as if this many countries had "
             "equal shares. Unlike a count of countries, it does not grow with the number of days or jobs."),
    ]
    return tiles


def period_text(data: DashboardData) -> dict:
    months = data.get("monthly_market_summary.csv")
    if months is None:
        return {}
    return {"first_day": months["first_day"].min(), "data_through": months["last_day"].max(),
            "days": int(months["days_observed"].sum()), "months": [r.label for r in months.itertuples()],
            "partial": bool(months["partial"].any())}


# ------------------------------------------------------------------ figures


def fig_weekly_volume(data: DashboardData) -> dict | None:
    weeks = data.get("weekly_market_summary.csv")
    if weeks is None:
        return None
    traces = []
    for complete, color, label in ((True, BLUE, "Complete week (7 days)"), (False, LIGHT_BLUE, "Partial week")):
        part = weeks[weeks["complete"] == complete]
        if part.empty:
            continue
        traces.append({"type": "bar", "name": label, "x": [week_label(r) for r in part.itertuples()],
                       "y": part["jobs_per_day"].round(0).tolist(), "marker": {"color": color},
                       "customdata": part[["days_observed", "jobs"]].values.tolist(),
                       "hovertemplate": "Week %{x}<br>%{y:,.0f} jobs per day<br>%{customdata[0]} days observed, "
                                        "%{customdata[1]:,} jobs<extra></extra>"})
    order = [week_label(r) for r in weeks.itertuples()]
    return {"data": traces, "layout": layout(barmode="overlay", bargap=0.35,
                                             xaxis={"categoryorder": "array", "categoryarray": order, "tickangle": 0},
                                             yaxis={"title": {"text": "Jobs per day"}, "rangemode": "tozero"})}


def fig_monthly_categories(data: DashboardData) -> dict | None:
    shares = data.get("monthly_category_share.csv")
    months = data.get("monthly_market_summary.csv")
    if shares is None or months is None:
        return None
    labels = dict(zip(months["month"], months["label"]))
    recent = list(months["month"])[-3:]
    order = (shares[shares["month"] == recent[-1]].sort_values("share_pct")["primary_category"].tolist())
    traces = []
    for color, month in zip(SERIES, recent):
        part = shares[shares["month"] == month].set_index("primary_category").reindex(order)
        traces.append({"type": "scatter", "mode": "markers", "name": labels[month],
                       "y": [name_of(c) for c in order], "x": part["share_pct"].round(2).tolist(),
                       "marker": {"color": color, "size": 10, "line": {"color": "#ffffff", "width": 2}},
                       "hovertemplate": "%{y}<br>" + labels[month] + ": %{x:.1f}% of jobs<extra></extra>"})
    return {"data": traces, "layout": layout(height=620, margin={"l": 190},
                                             xaxis={"title": {"text": "Share of the period's jobs (%)"}, "rangemode": "tozero"},
                                             yaxis={"automargin": True}, legend={"y": -0.12})}


def fig_weekly_category(data: DashboardData) -> tuple[dict | None, list[dict]]:
    shares = data.get("weekly_category_share.csv")
    weeks = data.get("weekly_market_summary.csv")
    if shares is None or weeks is None:
        return None, []
    labels = {r.iso_week: week_label(r) for r in weeks.itertuples()}
    days = dict(zip(weeks["iso_week"], weeks["days_observed"]))
    totals = shares.groupby("primary_category")["jobs"].sum().sort_values(ascending=False)
    categories = list(totals.index)
    default = next((c for c in categories if c != "other_unclear"), categories[0])
    traces = []
    for category in categories:
        part = shares[shares["primary_category"] == category].sort_values("iso_week")
        traces.append({"type": "scatter", "mode": "lines+markers", "name": name_of(category),
                       "x": [labels[w] for w in part["iso_week"]], "y": part["share_pct"].round(2).tolist(),
                       "customdata": [days[w] for w in part["iso_week"]], "visible": category == default,
                       "line": {"color": BLUE, "width": 2}, "marker": {"size": 8, "color": BLUE},
                       "hovertemplate": "%{x}<br>%{y:.2f}% of the week's jobs<br>%{customdata} days observed"
                                        "<extra>" + name_of(category) + "</extra>"})
    options = [{"value": i, "label": name_of(c), "selected": c == default} for i, c in enumerate(categories)]
    return {"data": traces, "layout": layout(showlegend=False,
                                             yaxis={"title": {"text": "Share of the week's jobs (%)"}, "rangemode": "tozero"},
                                             xaxis={"categoryorder": "array", "tickangle": 0,
                                                    "categoryarray": [labels[w] for w in sorted(labels)]})}, options


def fig_trend_tests(data: DashboardData) -> dict | None:
    table = data.get("trend_categories.csv")
    if table is None:
        return None
    table = table.sort_values("change_pp")
    status = pd.Series("No clear trend", index=table.index)
    status[(table["p_fdr"] < 0.05) & (table["change_pp"] > 0)] = "Rising (FDR q < 0.05)"
    status[(table["p_fdr"] < 0.05) & (table["change_pp"] < 0)] = "Falling (FDR q < 0.05)"
    traces = []
    for label, color in (("Rising (FDR q < 0.05)", BLUE), ("Falling (FDR q < 0.05)", RED), ("No clear trend", GREY)):
        part = table[status == label]
        if part.empty:
            continue
        traces.append({"type": "bar", "orientation": "h", "name": label,
                       "y": [name_of(c) for c in part["primary_category"]], "x": part["change_pp"].round(3).tolist(),
                       "marker": {"color": color},
                       "error_x": {"type": "data", "symmetric": False, "color": MUTED, "thickness": 1, "width": 3,
                                   "array": (part["change_high_pp"] - part["change_pp"]).round(3).tolist(),
                                   "arrayminus": (part["change_pp"] - part["change_low_pp"]).round(3).tolist()},
                       "customdata": part[["relative_change_pct", "p_fdr"]].round(4).values.tolist(),
                       "hovertemplate": "%{y}<br>%{x:+.2f} pp over the window (%{customdata[0]:+.1f}% relative)"
                                        "<br>FDR q = %{customdata[1]}<extra></extra>"})
    order = [name_of(c) for c in table["primary_category"]]
    return {"data": traces, "layout": layout(height=560, margin={"l": 190}, barmode="overlay",
                                             yaxis={"categoryorder": "array", "categoryarray": order, "automargin": True},
                                             xaxis={"title": {"text": "Change in share (percentage points)"},
                                                    "zeroline": True, "zerolinecolor": "#9a978f"},
                                             legend={"y": -0.1})}


def fig_pay_keywords(data: DashboardData, k: int = 10) -> dict | None:
    table = data.get("pay_keywords_hourly.csv")
    if table is None:
        return None
    supported = table[table["country_category_p_fdr"] < 0.05]
    top = supported.nlargest(k, "country_category_pct")
    bottom = supported.nsmallest(k, "country_category_pct")
    bottom = bottom[bottom["country_category_pct"] < 0]
    chosen = pd.concat([bottom, top[top["country_category_pct"] > 0]]).drop_duplicates("keyword")
    chosen = chosen.sort_values("country_category_pct")
    traces = []
    for label, color, part in (("Higher offers", BLUE, chosen[chosen["country_category_pct"] > 0]),
                               ("Lower offers", RED, chosen[chosen["country_category_pct"] < 0])):
        if part.empty:
            continue
        traces.append({"type": "bar", "orientation": "h", "name": label, "y": part["keyword"].tolist(),
                       "x": part["country_category_pct"].round(1).tolist(), "marker": {"color": color},
                       "customdata": part[["jobs", "median_with"]].values.tolist(),
                       "hovertemplate": "'%{y}': %{x:+.1f}% vs similar jobs (same country and category)"
                                        "<br>%{customdata[0]:,} jobs; median $%{customdata[1]}/hr<extra></extra>"})
    return {"data": traces, "layout": layout(height=560, margin={"l": 150}, barmode="overlay",
                                             yaxis={"categoryorder": "array", "categoryarray": chosen["keyword"].tolist(),
                                                    "automargin": True},
                                             xaxis={"title": {"text": "Hourly offer difference (%)"},
                                                    "zeroline": True, "zerolinecolor": "#9a978f"},
                                             legend={"y": -0.1})}


GEOJSON_URL = "/static/world_countries.geojson"


def map_country_ids() -> set[str]:
    """ISO3 codes drawn by the bundled Natural Earth (1:110m) outline (public domain)."""
    import json
    from importlib import resources

    try:
        text = resources.files("job_market_web").joinpath("static", "world_countries.geojson").read_text("utf-8")
    except (FileNotFoundError, OSError):
        return set()
    return {feature["id"] for feature in json.loads(text)["features"]}


def fig_country_map(data: DashboardData) -> tuple[dict | None, list[str]]:
    table = data.get("pay_countries.csv")
    if table is None:
        return None, []
    table = table.dropna(subset=["iso3"])
    drawable = map_country_ids()
    hidden = table.loc[~table["iso3"].isin(drawable), "country"].tolist() if drawable else []
    background = {"type": "choropleth", "geojson": GEOJSON_URL, "locations": sorted(drawable - {"ATA"}),
                  "z": [0] * len(drawable - {"ATA"}), "colorscale": [[0, "#efede8"], [1, "#efede8"]],
                  "showscale": False, "hoverinfo": "skip", "marker": {"line": {"color": "#ffffff", "width": 0.5}}}
    trace = {"type": "choropleth", "geojson": GEOJSON_URL, "locations": table["iso3"].tolist(),
             "z": table["median_rate"].tolist(), "text": table["country"].tolist(), "colorscale": SEQUENTIAL,
             "marker": {"line": {"color": "#ffffff", "width": 0.5}},
             "colorbar": {"title": {"text": "Median $/hr"}, "thickness": 12, "len": 0.7},
             "customdata": table[["jobs", "adjusted_index_pct"]].round(1).values.tolist(),
             "hovertemplate": "%{text}<br>Median offer: $%{z}/hr<br>%{customdata[0]:,} hourly jobs<br>"
                              "Adjusted index: %{customdata[1]:+.1f}% (same job types)<extra></extra>"}
    figure = {"data": [background, trace],
              "layout": layout(height=430, margin={"l": 0, "r": 0, "t": 0, "b": 0},
                               geo={"visible": False, "projection": {"type": "natural earth"},
                                    "lataxis": {"range": [-58, 85]}, "bgcolor": "rgba(0,0,0,0)"})}
    return figure, hidden


def forecast_shape(start: str, end: str) -> dict:
    return {"type": "rect", "xref": "x", "yref": "paper", "x0": start, "x1": end, "y0": 0, "y1": 1,
            "fillcolor": "rgba(93,96,102,0.07)", "line": {"width": 0}, "layer": "below"}


def fig_forecast_total(data: DashboardData) -> dict | None:
    observed = data.get("remote_daily.csv")
    forecast = data.get("forecast_demand_daily.csv")
    if observed is None or forecast is None:
        return None
    total = forecast[forecast["series"] == "total"].sort_values("date")
    if total.empty:
        return None
    traces = [
        {"type": "scatter", "mode": "lines", "name": "Observed jobs per day", "x": observed["date"].tolist(),
         "y": observed["jobs"].tolist(), "line": {"color": BLUE, "width": 2},
         "hovertemplate": "%{x|%a %d %b}<br>%{y:,} jobs observed<extra></extra>"},
        {"type": "scatter", "mode": "lines", "x": total["date"].tolist(), "y": total["high"].round(0).tolist(),
         "line": {"width": 0}, "showlegend": False, "hoverinfo": "skip"},
        {"type": "scatter", "mode": "lines", "name": "80% empirical range", "x": total["date"].tolist(),
         "y": total["low"].round(0).tolist(), "fill": "tonexty", "fillcolor": LIGHT_ORANGE, "line": {"width": 0},
         "hoverinfo": "skip"},
        {"type": "scatter", "mode": "lines+markers", "name": "Forecast (expected jobs)", "x": total["date"].tolist(),
         "y": total["forecast"].round(0).tolist(), "line": {"color": ORANGE, "width": 2, "dash": "dash"},
         "marker": {"size": 6}, "customdata": total[["low", "high", "horizon"]].round(0).values.tolist(),
         "hovertemplate": "%{x|%a %d %b} (day %{customdata[2]})<br>Forecast %{y:,.0f} jobs"
                          "<br>Range %{customdata[0]:,.0f} - %{customdata[1]:,.0f}<extra></extra>"},
    ]
    start, end = total["date"].min(), total["date"].max()
    return {"data": traces, "layout": layout(shapes=[forecast_shape(start, end)],
                                             annotations=[{"x": start, "xref": "x", "y": 1.0, "yref": "paper",
                                                           "text": "Forecast", "showarrow": False, "xanchor": "left",
                                                           "yanchor": "top", "font": {"color": MUTED}}],
                                             yaxis={"title": {"text": "Jobs per day"}, "rangemode": "tozero"},
                                             hovermode="x unified")}


def fig_signals(data: DashboardData) -> dict | None:
    observed = data.get("remote_daily.csv")
    forecast = data.get("forecast_signals_daily.csv")
    if observed is None:
        return None
    traces, end = [], None
    for column, label, color in (("hourly_share", "Hourly share", BLUE),
                                 ("north_america_share", "North American client share", ORANGE)):
        traces.append({"type": "scatter", "mode": "lines", "name": f"{label} (observed)", "x": observed["date"].tolist(),
                       "y": (100 * observed[column]).round(2).tolist(), "line": {"color": color, "width": 2},
                       "hovertemplate": "%{x|%d %b}: %{y:.1f}%<extra>" + label + "</extra>"})
        if forecast is not None:
            part = forecast[forecast["series"] == column].sort_values("date")
            if not part.empty:
                end = part["date"].max()
                traces.append({"type": "scatter", "mode": "lines", "name": f"{label} (forecast)",
                               "x": part["date"].tolist(), "y": (100 * part["forecast"]).round(2).tolist(),
                               "line": {"color": color, "width": 2, "dash": "dash"},
                               "customdata": (100 * part[["low", "high"]]).round(1).values.tolist(),
                               "hovertemplate": "%{x|%d %b}: forecast %{y:.1f}% (range %{customdata[0]} - "
                                                "%{customdata[1]})<extra>" + label + "</extra>"})
    shapes = []
    if end is not None:
        start = forecast["date"].min()
        shapes = [forecast_shape(start, end)]
    return {"data": traces, "layout": layout(shapes=shapes, yaxis={"title": {"text": "Share of jobs (%)"}},
                                             legend={"y": -0.22})}


# ------------------------------------------------------------------ tables


def outlook_rows(data: DashboardData) -> list[dict]:
    table = data.get("forecast_demand_outlook.csv")
    if table is None:
        return []
    table = table[table["series"] != "total"].sort_values("rank_1_7")
    return [{"category": name_of(r.series), "recent": f"{r.recent_jobs_per_day:,.0f}",
             "forecast": f"{r.forecast_jobs_per_day_1_7:,.0f}",
             "range": f"{r.low_1_7:,.0f} - {r.high_1_7:,.0f}",
             "direction": str(r.direction).capitalize() if isinstance(r.direction, str) else "No reliable direction"}
            for r in table.itertuples()]


def signal_rows(data: DashboardData) -> list[dict]:
    table = data.get("forecast_signals_outlook.csv")
    if table is None:
        return []
    names = {"hourly_share": ("Hourly share", True), "north_america_share": ("North American client share", True),
             "hhi": ("Effective number of countries", False)}
    rows = []
    for r in table.itertuples():
        label, is_share = names.get(r.series, (r.series, True))
        fmt = (lambda v: f"{100 * v:.1f}%") if is_share else (lambda v: f"{1 / v:.2f}")
        rows.append({"signal": label, "recent": fmt(r.recent_value), "forecast": fmt(r.forecast_1_14),
                     "direction": str(r.direction).capitalize()})
    return rows


def top_countries(data: DashboardData, k: int = 8) -> dict:
    table = data.get("monthly_country_share.csv")
    months = data.get("monthly_market_summary.csv")
    if table is None or months is None:
        return {}
    recent = list(months["month"])[-2:]
    labels = dict(zip(months["month"], months["label"]))
    order = table[table["month"] == recent[-1]].nsmallest(k, "rank")["country"].tolist()
    rows = []
    for country in order:
        values = []
        for month in recent:
            hit = table[(table["month"] == month) & (table["country"] == country)]["share_pct"]
            values.append(f"{hit.iloc[0]:.1f}%" if len(hit) else "-")
        rows.append({"country": country, "cells": values})
    return {"months": [labels[m] for m in recent], "rows": rows}


def clean_json(value: Any) -> Any:
    """Replace NaN and infinity (not valid JSON) with None, recursively."""
    if isinstance(value, dict):
        return {k: clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        return clean_json(value.item())
    return value


def context(data: DashboardData) -> dict:
    """Everything the dashboard template needs."""
    weekly_category, category_options = fig_weekly_category(data)
    country_map, hidden_countries = fig_country_map(data)
    figures = {
        "weekly_volume": fig_weekly_volume(data), "monthly_categories": fig_monthly_categories(data),
        "weekly_category": weekly_category, "trend_tests": fig_trend_tests(data),
        "pay_keywords": fig_pay_keywords(data), "country_map": country_map,
        "forecast_total": fig_forecast_total(data), "signals": fig_signals(data),
    }
    forecast = data.get("forecast_demand_daily.csv")
    return {
        "build_id": data.build_id, "period": period_text(data), "tiles": headline_tiles(data),
        "figures": clean_json({k: v for k, v in figures.items() if v is not None}),
        "category_options": category_options, "outlook": outlook_rows(data), "signals": signal_rows(data),
        "countries": top_countries(data), "hidden_countries": hidden_countries,
        "forecast_period": ({"start": forecast["date"].min(), "end": forecast["date"].max()}
                            if forecast is not None else None),
        "months": data.get("monthly_market_summary.csv").to_dict("records")
        if data.get("monthly_market_summary.csv") is not None else [],
    }
