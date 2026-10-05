"""SQLite database and SQL cross-checks (decision D-037).

The pipeline's ``database`` step writes ``data/processed/job_market.sqlite``
from ``sql/schema.sql``: row-level tables (jobs, category predictions, human
labels, recommendation rankings) plus a ``build_info`` table. The numbered
queries in ``sql/`` recompute selected aggregations and evaluation metrics
from those rows. SQL independently reproduces selected aggregations and
evaluation metrics from the pipeline's verified row-level outputs; the
cleaned fields, category predictions and recommendation rankings themselves
come from the Python pipeline.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

SCHEMA_VERSION = "1"
SCHEMA_FILE = "schema.sql"
DATABASE_FILE = "job_market.sqlite"
JOB_COLUMNS = ["row_id", "title_key", "posted_date", "iso_week", "contract_type", "hourly_low", "hourly_high",
               "hourly_mid", "budget", "country", "eligible_for_timeseries", "eligible_for_hourly_rate_analysis"]
FLOAT_TOLERANCE = 1e-9


def sql_dir(root: Path) -> Path:
    return Path(root) / "sql"


def query_files(root: Path) -> list[Path]:
    """The numbered query files, in order (schema.sql excluded)."""
    return sorted(p for p in sql_dir(root).glob("[0-9][0-9]_*.sql"))


def sql_sha256(root: Path) -> str | None:
    """Fingerprint of every .sql file (line endings normalised), or None when the folder is absent."""
    folder = sql_dir(root)
    if not folder.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(folder.glob("*.sql")):
        text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        digest.update(path.name.encode("utf-8") + b"\0" + text.encode("utf-8") + b"\0")
    return digest.hexdigest()


def jobs_table(clean: pd.DataFrame) -> pd.DataFrame:
    table = clean[JOB_COLUMNS].copy()
    table["posted_date"] = pd.to_datetime(table["posted_date"]).dt.strftime("%Y-%m-%d")
    for column in ("title_key", "iso_week", "contract_type", "country"):
        table[column] = table[column].astype(object).where(table[column].notna(), None)
    for column in ("eligible_for_timeseries", "eligible_for_hourly_rate_analysis"):
        table[column] = table[column].astype(bool).astype(int)
    return table


def write_database(path: Path, schema: str, tables: dict[str, pd.DataFrame], build_info: dict[str, str]) -> Path:
    """Delete any old file, create the schema and load the tables (all or nothing)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(schema)
        with connection:
            connection.executemany("INSERT INTO build_info (key, value) VALUES (?, ?)", sorted(build_info.items()))
            for name, table in tables.items():
                if len(table):
                    columns = list(table.columns)
                    placeholders = ", ".join("?" for _ in columns)
                    rows = (tuple(None if pd.isna(v) else v for v in row)
                            for row in table.itertuples(index=False, name=None))
                    connection.executemany(f"INSERT INTO {name} ({', '.join(columns)}) VALUES ({placeholders})", rows)
        connection.execute("VACUUM")
    finally:
        connection.close()
    return path


def read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)


def run_query(path: Path, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    connection = read_only(path)
    try:
        return pd.read_sql_query(sql, connection, params=params or {})
    finally:
        connection.close()


def matches_build(info: dict[str, str], manifest: dict) -> bool:
    """True when the database's recorded input fingerprints equal the build's."""
    recorded = manifest.get("fingerprints", {})
    return bool(recorded) and all(info.get(key, "") == (value or "") for key, value in recorded.items())


def build_info(path: Path) -> dict[str, str]:
    connection = read_only(path)
    try:
        return dict(connection.execute("SELECT key, value FROM build_info").fetchall())
    finally:
        connection.close()


STORED_DECIMALS = 6


def compare(sql: pd.DataFrame, python: pd.DataFrame, keys: list[str], exact: list[str], close: list[str],
            stored_decimals: int | None = STORED_DECIMALS, tolerance: float = FLOAT_TOLERANCE) -> pd.DataFrame:
    """One row per compared value: counts must be equal, decimals must agree.

    The pipeline's CSV tables store decimals rounded to ``stored_decimals``
    places, so an exact value from SQL can differ from the stored value by at
    most half a unit in that place. A decimal passes when
    ``|sql - python| <= 0.5 * 10**-stored_decimals + tolerance``; with
    ``stored_decimals=None`` (unrounded Python values) the limit is ``tolerance``.
    Rows are matched on ``keys``; a row present on one side only is a failure.
    """
    limit = tolerance + (0.5 * 10 ** -stored_decimals if stored_decimals is not None else 0.0)
    merged = sql.merge(python, on=keys, how="outer", suffixes=("_sql", "_python"), indicator=True)
    rows = []
    for _, row in merged.iterrows():
        key = " / ".join(str(row[k]) for k in keys)
        if row["_merge"] != "both":
            rows.append({"key": key, "value": "(row)", "sql": None, "python": None, "difference": None,
                         "passed": False})
            continue
        for column in exact + close:
            a, b = row[f"{column}_sql"], row[f"{column}_python"]
            if pd.isna(a) and pd.isna(b):
                passed, difference = True, 0.0
            elif pd.isna(a) or pd.isna(b):
                passed, difference = False, None
            elif column in exact:
                passed, difference = bool(int(a) == int(b)), float(a) - float(b)
            else:
                difference = float(a) - float(b)
                passed = abs(difference) <= limit
            rows.append({"key": key, "value": column, "sql": a, "python": b, "difference": difference,
                         "passed": passed})
    return pd.DataFrame(rows, columns=["key", "value", "sql", "python", "difference", "passed"])
