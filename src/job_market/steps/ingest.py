"""Step 1 - ingest: load the raw CSV, validate its schema, and profile it.

This step changes no values. It checks that the file has the expected shape,
records what the raw data looks like, and hands a typed copy to later steps.
Every cleaning decision happens later, in the cleaning step, where each rule
is documented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import Settings
from ..io import write_csv
from ..manifest import StepRecord, describe_output

NAME = "ingest"
DESCRIPTION = "Load the raw CSV, validate the schema, and profile columns and daily coverage."

TEXT_COLUMNS = ("title", "link", "published_date", "country")
NUMERIC_COLUMNS = ("hourly_low", "hourly_high", "budget")


class SchemaError(ValueError):
    """Raised when the raw file does not match the expected schema."""


def read_raw(path: Path, required_columns: list[str]) -> pd.DataFrame:
    """Read the raw CSV with explicit, version-stable types.

    Only empty cells count as missing. By default pandas also treats strings
    such as "NA", "None" or "null" as missing, which can silently erase real
    values (for example the country code "NA" for Namibia). Reading with
    ``keep_default_na=False`` prevents that.
    """
    frame = pd.read_csv(
        path,
        keep_default_na=False,
        na_values=[""],
        dtype={column: "object" for column in TEXT_COLUMNS},
    )
    validate_schema(frame, required_columns)
    frame["is_hourly"] = _parse_boolean(frame["is_hourly"])
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype("float64")
    return frame


def validate_schema(frame: pd.DataFrame, required_columns: list[str]) -> None:
    """Fail loudly if columns are missing, unexpected, or duplicated."""
    columns = list(frame.columns)
    missing = sorted(set(required_columns) - set(columns))
    unexpected = sorted(set(columns) - set(required_columns))
    duplicated = sorted({c for c in columns if columns.count(c) > 1})
    problems = []
    if missing:
        problems.append(f"missing columns: {missing}")
    if unexpected:
        problems.append(f"unexpected columns: {unexpected}")
    if duplicated:
        problems.append(f"duplicated columns: {duplicated}")
    if problems:
        raise SchemaError("Raw file schema check fails - " + "; ".join(problems))


def _parse_boolean(series: pd.Series) -> pd.Series:
    """Convert the contract flag to a strict boolean; any other value is an error."""
    if series.dtype == bool:
        return series
    mapping = {"true": True, "false": False}
    lowered = series.astype(str).str.strip().str.lower()
    unknown = sorted(set(lowered.unique()) - set(mapping))
    if unknown:
        raise SchemaError(f"is_hourly contains values other than True/False: {unknown[:5]}")
    return lowered.map(mapping).astype(bool)


def parse_timestamps(series: pd.Series) -> pd.Series:
    """Parse ISO 8601 timestamps to timezone-aware UTC values; failures become NaT.

    An explicit format means every value follows one parsing rule, instead of
    pandas guessing a format and falling back to value-by-value parsing.
    """
    return pd.to_datetime(series, errors="coerce", utc=True, format="ISO8601")


def require_timestamps(timestamps: pd.Series) -> None:
    """Stop with a clear message when no timestamp at all can be parsed.

    Individual unparseable values are counted and reported; a file with no
    usable timestamp cannot support any time-based analysis.
    """
    if timestamps.notna().sum() == 0:
        raise SchemaError("published_date contains no parseable timestamps")


def column_profile(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per column: type, missing count and share, distinct values."""
    rows = []
    total = len(frame)
    for column in frame.columns:
        values = frame[column]
        missing = int(values.isna().sum())
        rows.append(
            {
                "column": column,
                "dtype": str(values.dtype),
                "non_missing": total - missing,
                "missing": missing,
                "missing_pct": round(100.0 * missing / total, 4) if total else 0.0,
                "distinct_values": int(values.nunique(dropna=True)),
            }
        )
    return pd.DataFrame(rows)


def daily_coverage(timestamps: pd.Series) -> pd.DataFrame:
    """Postings per UTC day, with the first and last timestamp seen that day.

    The first and last timestamps reveal partial collection days: a normal day
    spans close to 24 hours, while a day where collection starts late or stops
    early spans far less.
    """
    valid = timestamps.dropna()
    frame = pd.DataFrame({"ts": valid, "date": valid.dt.strftime("%Y-%m-%d")})
    grouped = frame.groupby("date")["ts"]
    out = pd.DataFrame(
        {
            "postings": grouped.size(),
            "first_posting_utc": grouped.min().dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_posting_utc": grouped.max().dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    span = (grouped.max() - grouped.min()).dt.total_seconds() / 3600.0
    out["observed_span_hours"] = span.round(2)
    return out.reset_index().sort_values("date").reset_index(drop=True)


def run(settings: Settings, context: dict[str, Any]) -> StepRecord:
    """Execute the ingest step and store the typed raw frame in ``context``."""
    record = StepRecord(NAME, DESCRIPTION)
    raw_path = settings.path("raw_csv")
    if not raw_path.is_file():
        raise FileNotFoundError(f"Raw CSV not found at {raw_path}")

    frame = read_raw(raw_path, list(settings.section("schema")["required_columns"]))
    timestamps = parse_timestamps(frame["published_date"])
    require_timestamps(timestamps)

    processed = settings.path("processed_dir")
    profile = column_profile(frame)
    coverage = daily_coverage(timestamps)
    profile_path = write_csv(profile, processed / "raw_column_profile.csv")
    coverage_path = write_csv(coverage, processed / "raw_daily_coverage.csv")
    record.outputs.append(describe_output(profile_path, settings.root, rows=len(profile)))
    record.outputs.append(describe_output(coverage_path, settings.root, rows=len(coverage)))

    links = frame["link"]
    record.metrics = {
        "raw_rows": int(len(frame)),
        "raw_columns": int(frame.shape[1]),
        "hourly_rows": int(frame["is_hourly"].sum()),
        "fixed_price_rows": int((~frame["is_hourly"]).sum()),
        "missing_title": int(frame["title"].isna().sum()),
        "missing_link": int(links.isna().sum()),
        "duplicate_links_non_missing": int(links.dropna().duplicated().sum()),
        "exact_duplicate_rows": int(frame.duplicated().sum()),
        "unparseable_timestamps": int(timestamps.isna().sum()),
        "first_posting_utc": timestamps.min().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_posting_utc": timestamps.max().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "calendar_days_with_postings": int(len(coverage)),
        "negative_numeric_values": int(sum(int((frame[c] < 0).sum()) for c in NUMERIC_COLUMNS)),
        "non_finite_numeric_values": int(sum(int(np.isinf(frame[c]).sum()) for c in NUMERIC_COLUMNS)),
    }

    context["source"].update({"rows": int(len(frame)), "columns": list(frame.columns)})
    context["raw"] = frame
    context["raw_timestamps"] = timestamps
    return record
