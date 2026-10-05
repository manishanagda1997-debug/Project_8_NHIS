"""Step 9 - monitor: monthly and weekly tables for the Task 6 dashboard (decision D-036).

Summarises the reliable time-series window by calendar month and ISO week:
volume (raw and weekday-standardized jobs per day), hourly share, median
hourly rate, client-country concentration, and category and country shares.
The dashboard only reads these tables; a rebuild with newer data adds new
months and weeks without any code change.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..io import write_csv
from ..manifest import StepRecord, describe_output
from ..monitor import COLUMNS, group_shares, monthly_summary, prepare, weekly_summary

NAME = "monitor"
DESCRIPTION = "Monthly and weekly market tables for the dashboard (Task 6)."


def run(settings: Settings, context: dict[str, Any]) -> StepRecord:
    record = StepRecord(NAME, DESCRIPTION)
    clean = context["clean"]
    frame = clean.loc[clean["eligible_for_timeseries"], [c for c in COLUMNS if c != "primary_category"]]
    frame = frame.merge(context["categories"][["row_id", "primary_category"]], on="row_id", how="left",
                        validate="one_to_one")
    if frame.empty:
        record.metrics["monitor_skipped"] = "no jobs in the time-series window"
        return record
    frame = prepare(frame)
    outputs = {
        "monthly_market_summary.csv": monthly_summary(frame),
        "monthly_category_share.csv": group_shares(frame, "month", "primary_category"),
        "monthly_country_share.csv": group_shares(frame, "month", "country", known_only=True),
        "weekly_market_summary.csv": weekly_summary(frame),
        "weekly_category_share.csv": group_shares(frame, "iso_week", "primary_category"),
    }
    processed = settings.path("processed_dir")
    for name, table in outputs.items():
        path = write_csv(table.round(6), processed / name)
        record.outputs.append(describe_output(path, settings.root, rows=len(table)))
    months = outputs["monthly_market_summary.csv"]
    record.metrics = {"monitor_months": len(months), "monitor_weeks": len(outputs["weekly_market_summary.csv"]),
                      "monitor_first_day": months["first_day"].min(), "monitor_data_through": months["last_day"].max()}
    return record
