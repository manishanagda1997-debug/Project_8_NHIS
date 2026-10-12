"""Draw the eight figures of the final report from the committed result tables.

Run from the project root:

    python reports/make_figures.py

Every figure reads only the CSV tables in ``data/processed/`` that the
pipeline writes and Git keeps, so the figures can be redrawn without the raw
data. Nothing here computes a new result: the script only draws numbers that
the pipeline and the notebooks already produce and check.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from job_market.taxonomy import CATEGORIES, OTHER  # noqa: E402

DATA = ROOT / "data" / "processed"
OUT = ROOT / "reports" / "figures"

NAMES = {key: name for key, (name, _) in CATEGORIES.items()}
NAMES[OTHER] = "Other / Unclear"

INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
BLUE, BLUE_LIGHT, ORANGE, GREY = "#2a78d6", "#a9c8ef", "#eb6834", "#b8b6b0"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9.5, "figure.dpi": 100, "savefig.dpi": 200,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False, "text.color": INK,
})


def read(name: str, **kwargs) -> pd.DataFrame:
    return pd.read_csv(DATA / name, **kwargs)


def save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", facecolor="white", metadata={"Software": None})
    plt.close(fig)
    return path


def f1_daily_volume() -> Path:
    days = read("day_quality.csv", parse_dates=["date"])
    days = days[days["in_timeseries_window"]]
    jobs = read("remote_daily.csv", parse_dates=["date"]).set_index("date")["jobs"]
    weekend = days["weekday"].isin(["Saturday", "Sunday"]).to_numpy()
    fig, ax = plt.subplots(figsize=(8, 3.3))
    ax.bar(days["date"], jobs.reindex(days["date"]).to_numpy(), width=0.8,
           color=[BLUE_LIGHT if w else BLUE for w in weekend])
    gaps = days[days["status"] == "intraday_gap"]
    ax.scatter(gaps["date"], jobs.reindex(gaps["date"]).to_numpy() + 250, marker="v", s=28, color=INK, zorder=3)
    ax.set_ylabel("Jobs per day")
    ax.grid(axis="x", visible=False)
    ax.legend(handles=[Patch(color=BLUE, label="Monday to Friday"), Patch(color=BLUE_LIGHT, label="Saturday and Sunday"),
                       plt.Line2D([], [], marker="v", ls="", color=INK, label="Day with a small intraday gap")],
              loc="upper left", bbox_to_anchor=(0, 1.16), ncol=3)
    ax.xaxis.set_major_locator(matplotlib.dates.WeekdayLocator(byweekday=matplotlib.dates.MO))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%a %d %b"))
    return save(fig, "f1_daily_volume.png")


def f2_pay_keywords(per_side: int = 12) -> Path:
    kw = read("pay_keywords_hourly.csv")
    sig = kw[kw["country_category_p_fdr"] < 0.05]
    top = pd.concat([sig.nlargest(per_side, "country_category_pct"), sig.nsmallest(per_side, "country_category_pct")])
    top = top.sort_values("country_category_pct")
    fig, ax = plt.subplots(figsize=(8, 6.2))
    colors = [BLUE if v > 0 else ORANGE for v in top["country_category_pct"]]
    y = range(len(top))
    ax.barh(y, top["country_category_pct"], color=colors, height=0.68)
    ax.errorbar(top["country_category_pct"], y,
                xerr=[top["country_category_pct"] - top["country_category_low_pct"],
                      top["country_category_high_pct"] - top["country_category_pct"]],
                fmt="none", ecolor=INK, elinewidth=0.9, capsize=2)
    ax.set_yticks(list(y), top["keyword"])
    ax.axvline(0, color=MUTED, lw=0.9)
    ax.set_xlabel("Difference in hourly offer compared with jobs in the same country and category (%)")
    ax.grid(axis="y", visible=False)
    ax.legend(handles=[Patch(color=BLUE, label="Higher offers"), Patch(color=ORANGE, label="Lower offers")],
              loc="lower right")
    return save(fig, "f2_pay_keywords.png")


def f3_category_trends() -> Path:
    t = read("trend_categories.csv").sort_values("change_pp")
    sig = t["p_fdr"] < 0.05
    colors = [GREY if not s else (BLUE if v > 0 else ORANGE) for s, v in zip(sig, t["change_pp"])]
    fig, ax = plt.subplots(figsize=(8, 6))
    y = range(len(t))
    ax.barh(y, t["change_pp"], color=colors, height=0.68)
    ax.errorbar(t["change_pp"], y, xerr=[t["change_pp"] - t["change_low_pp"], t["change_high_pp"] - t["change_pp"]],
                fmt="none", ecolor=INK, elinewidth=0.9, capsize=2)
    ax.set_yticks(list(y), [NAMES[c] for c in t["primary_category"]])
    ax.axvline(0, color=MUTED, lw=0.9)
    ax.set_xlabel("Change in share of daily postings over the window (percentage points)")
    ax.grid(axis="y", visible=False)
    ax.legend(handles=[Patch(color=BLUE, label="Rising (FDR 5%)"), Patch(color=ORANGE, label="Falling (FDR 5%)"),
                       Patch(color=GREY, label="No clear trend")], loc="lower right")
    return save(fig, "f3_category_trends.png")


def f4_category_outlook() -> Path:
    o = read("forecast_demand_outlook.csv")
    o = o[o["series"] != "total"].sort_values("forecast_jobs_per_day_1_7")
    other = (o["series"] == OTHER).to_numpy()
    fig, ax = plt.subplots(figsize=(8, 6.4))
    y = range(len(o))
    ax.barh(y, o["forecast_jobs_per_day_1_7"], color=[GREY if x else BLUE for x in other], height=0.68)
    ax.errorbar(o["forecast_jobs_per_day_1_7"], y,
                xerr=[o["forecast_jobs_per_day_1_7"] - o["low_1_7"], o["high_1_7"] - o["forecast_jobs_per_day_1_7"]],
                fmt="none", ecolor=INK, elinewidth=0.9, capsize=2)
    ax.set_yticks(list(y), [NAMES[s] for s in o["series"]])
    ax.set_xlabel("Forecast jobs per day, 24 to 30 March 2024 (intended 80% range)")
    ax.grid(axis="y", visible=False)
    ax.legend(handles=[Patch(color=BLUE, label="Job function"), Patch(color=GREY, label="Other / Unclear (not ranked)")],
              loc="lower right")
    return save(fig, "f4_category_outlook.png")


def f5_country_rates(top_n: int = 15) -> Path:
    c = read("pay_countries.csv").nlargest(top_n, "jobs").iloc[::-1]
    y = range(len(c))
    fig, (left, right) = plt.subplots(1, 2, figsize=(8, 5.2), sharey=True, gridspec_kw={"wspace": 0.08})
    left.errorbar(c["median_rate"], y, xerr=[c["median_rate"] - c["median_low"], c["median_high"] - c["median_rate"]],
                  fmt="o", color=BLUE, ecolor=MUTED, elinewidth=1, capsize=2, markersize=6)
    left.set_yticks(list(y), c["country"])
    left.set_xlabel("Median hourly offer (USD)")
    left.set_title("Median offer", fontsize=10)
    idx = c["adjusted_index_pct"]
    right.barh(y, idx, color=[BLUE if v > 0 else ORANGE for v in idx], height=0.66)
    right.errorbar(idx, y, xerr=[idx - c["adjusted_low_pct"], c["adjusted_high_pct"] - idx],
                   fmt="none", ecolor=INK, elinewidth=0.9, capsize=2)
    right.axvline(0, color=MUTED, lw=0.9)
    right.set_xlabel("Adjusted index: same job categories (%)")
    right.set_title("Adjusted for job mix", fontsize=10)
    for ax in (left, right):
        ax.grid(axis="y", visible=False)
    return save(fig, "f5_country_rates.png")


def f6_recommender_eval() -> Path:
    s = read("recommend_relevance_summary.csv")
    labels = {"keyword": "Keyword overlap", "tfidf_word": "Word TF-IDF", "tfidf_hybrid": "Hybrid TF-IDF (selected)"}
    s = s.set_index("method").loc[["keyword", "tfidf_word", "tfidf_hybrid"]]
    y = range(len(s))
    fig, axes = plt.subplots(1, 2, figsize=(8, 2.7), sharey=True, gridspec_kw={"wspace": 0.1})
    for ax, column, title in zip(axes, ["mean_ndcg", "mean_precision"], ["Mean nDCG@5", "Mean strict Precision@5"]):
        ax.scatter(s[column], list(y), s=60, zorder=3,
                   color=[BLUE if bool(w) else MUTED for w in s["winner"]])
        for yi, v in zip(y, s[column]):
            ax.annotate(f"{v:.3f}", (v, yi), xytext=(7, -3), textcoords="offset points", fontsize=8.5, color=INK)
        ax.set_xlim(0.90, 1.005)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="y", visible=False)
    margin = s["mean_ndcg"].max() - 0.02
    axes[0].axvline(margin, color=MUTED, ls="--", lw=1)
    axes[0].annotate("tie margin: 0.02 below\nthe best nDCG@5", (margin, 2.25), xytext=(-5, 0),
                     textcoords="offset points", ha="right", va="center", fontsize=8.5, color=INK)
    axes[0].set_yticks(list(y), [labels[m] for m in s.index])
    axes[0].set_ylim(-0.5, 2.6)
    return save(fig, "f6_recommender_eval.png")


def signal_panel(ax, observed: pd.Series, forecast: pd.DataFrame, ylabel: str) -> None:
    ax.plot(observed.index, 100 * observed, color=BLUE, lw=2, label="Observed")
    first, second = forecast[forecast["horizon"] <= 7], forecast[forecast["horizon"] >= 7]
    ax.fill_between(first["date"], 100 * first["low"], 100 * first["high"], color=BLUE_LIGHT, alpha=0.8,
                    lw=0, label="Intended 80% range (days 1 to 7)")
    ax.fill_between(second["date"], 100 * second["low"], 100 * second["high"], color=BLUE_LIGHT, alpha=0.4,
                    lw=0, hatch="///", edgecolor="white", label="Extended range (days 8 to 14)")
    ax.plot(forecast["date"], 100 * forecast["forecast"], color=BLUE, lw=2, ls="--", label="Forecast")
    ax.axvline(forecast["date"].min(), color=MUTED, lw=0.8, ls=":")
    ax.set_ylabel(ylabel)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d %b"))


def f7_online_signals() -> Path:
    daily = read("remote_daily.csv", parse_dates=["date"]).set_index("date")
    fc = read("forecast_signals_daily.csv", parse_dates=["date"])
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(8, 5.4), sharex=True, gridspec_kw={"hspace": 0.18})
    signal_panel(top, daily["hourly_share"], fc[fc["series"] == "hourly_share"], "Hourly share of jobs (%)")
    signal_panel(bottom, daily["north_america_share"], fc[fc["series"] == "north_america_share"],
                 "North American clients (%)")
    top.legend(loc="upper left", bbox_to_anchor=(0, 1.3), ncol=2)
    return save(fig, "f7_online_signals.png")


def f8_total_outlook() -> Path:
    daily = read("remote_daily.csv", parse_dates=["date"]).set_index("date")["jobs"]
    fc = read("forecast_demand_daily.csv", parse_dates=["date"])
    fc = fc[fc["series"] == "total"]
    first, second = fc[fc["horizon"] <= 7], fc[fc["horizon"] >= 7]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(daily.index, daily.to_numpy(), color=BLUE, lw=2, label="Observed")
    ax.fill_between(first["date"], first["low"], first["high"], color=BLUE_LIGHT, alpha=0.8, lw=0,
                    label="Intended 80% range (days 1 to 7)")
    ax.fill_between(second["date"], second["low"], second["high"], color=BLUE_LIGHT, alpha=0.4, lw=0,
                    hatch="///", edgecolor="white", label="Extended range (days 8 to 14)")
    ax.plot(fc["date"], fc["forecast"], color=BLUE, lw=2, ls="--", label="Central forecast")
    ax.axvline(fc["date"].min(), color=MUTED, lw=0.8, ls=":")
    ax.set_ylabel("Jobs per day")
    ax.set_ylim(0, None)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d %b"))
    ax.legend(loc="upper left", bbox_to_anchor=(0, 1.25), ncol=2)
    return save(fig, "f8_total_outlook.png")


FIGURES = [f1_daily_volume, f2_pay_keywords, f3_category_trends, f4_category_outlook,
           f5_country_rates, f6_recommender_eval, f7_online_signals, f8_total_outlook]


def main() -> None:
    for draw in FIGURES:
        print("wrote", draw().relative_to(ROOT))


if __name__ == "__main__":
    main()
