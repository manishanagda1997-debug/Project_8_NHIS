"""Step 10 - database: write the SQLite database for the SQL cross-checks (decision D-037).

The file is deleted and recreated from ``sql/schema.sql`` on every build, so
no stale rows survive. It holds row-level tables only (no summary tables) and
a ``build_info`` table with the build's input fingerprints. It is large and regenerable, so it is
not committed to Git.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..config import Settings
from ..database import DATABASE_FILE, SCHEMA_FILE, SCHEMA_VERSION, jobs_table, sql_dir, sql_sha256, write_database
from ..labels import LabelSheetError, read_label_sheet, read_relevance_sheet
from ..manifest import StepRecord, describe_output
from .evaluate import LABEL_SETS
from .recommend import RELEVANCE_SHEET

NAME = "database"
DESCRIPTION = "SQLite database of row-level tables for the SQL cross-checks."


def category_labels(settings: Settings) -> pd.DataFrame:
    frames = []
    for label_set, file_name in LABEL_SETS:
        try:
            labels = read_label_sheet(settings.path("labels_dir") / file_name)
        except LabelSheetError:
            continue
        frames.append(pd.DataFrame({"label_set": label_set, "sample_id": labels["sample_id"].astype(str),
                                    "row_id": labels["row_id"].astype(int),
                                    "human_category": labels["category"].astype(str)}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def relevance_tables(settings: Settings) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        labels = read_relevance_sheet(settings.path("labels_dir") / RELEVANCE_SHEET)
    except LabelSheetError:
        return pd.DataFrame(), pd.DataFrame()
    results_path = settings.path("processed_dir") / "recommend_relevance_items.csv"
    if not results_path.is_file() or results_path.stat().st_size == 0:
        return pd.DataFrame(), pd.DataFrame()
    results = pd.read_csv(results_path)
    if results.empty:
        return pd.DataFrame(), pd.DataFrame()
    judged = labels[["profile_id", "title_key", "relevance"]].astype({"relevance": int})
    ranked = results[["profile_id", "method", "rank", "row_id", "title_key"]].astype({"rank": int, "row_id": int})
    return judged, ranked


def run(settings: Settings, context: dict[str, Any]) -> StepRecord:
    record = StepRecord(NAME, DESCRIPTION)
    schema_path = sql_dir(settings.root) / SCHEMA_FILE
    if not schema_path.is_file():
        record.metrics["database_skipped"] = "sql/schema.sql is missing"
        return record
    jobs = jobs_table(context["clean"])
    categories = context["categories"][["row_id", "primary_category"]].astype({"primary_category": str})
    labels = category_labels(settings)
    judged, ranked = relevance_tables(settings)
    tables = {"jobs": jobs, "job_categories": categories, "category_labels": labels,
              "relevance_labels": judged, "recommendation_results": ranked}
    # Identity by content, not by time: the build fingerprints (raw data, settings, code, environment,
    # SQL) name exactly what produced the file, and a rebuild from the same inputs stays byte-identical.
    fingerprints = context.get("fingerprints") or {"source_sha256": context["source"]["sha256"],
                                                   "sql_sha256": sql_sha256(settings.root)}
    info = {"schema_version": SCHEMA_VERSION, **{key: value or "" for key, value in fingerprints.items()}}
    path = write_database(settings.path("processed_dir") / DATABASE_FILE, schema_path.read_text(encoding="utf-8"),
                          tables, info)
    record.outputs.append(describe_output(path, settings.root, rows=len(jobs)))
    record.metrics.update({"database_schema_version": SCHEMA_VERSION,
                           **{f"database_rows_{name}": len(table) for name, table in tables.items()}})
    return record
