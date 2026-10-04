"""Step 4 - evaluate: score the frozen categories against the human labels.

The label sheets in ``data/labels`` are inputs written by a person; this step
only reads them. A sheet that is missing or not completely filled in is
skipped (so a fresh clone without labels, or the test project, still builds),
and the step records which sets it scored.

The development set tuned the categorizer, so its score is optimistic. The
blind set is the honest result (decisions D-027 and D-029). Each sheet's
SHA-256 is recorded, so the manifest proves which labels produced the scores.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..config import Settings
from ..evaluate import confusion, per_category, score_items, summary_rows
from ..io import write_csv
from ..labels import LabelSheetError, read_label_sheet
from ..manifest import StepRecord, describe_output, sha256_file

NAME = "evaluate"
DESCRIPTION = "Score the job categories against the development and blind human labels."

LABEL_SETS = (("dev", "dev_labels.xlsx"), ("blind", "blind_labels.xlsx"))
ITEM_COLUMNS = (
    "label_set", "sample_id", "row_id", "title", "human", "predicted", "rules_only", "correct",
    "correct_rules_only", "category_method", "rule_score", "classifier_category", "classifier_probability",
    "matched_terms", "unsure", "note",
)


def run(settings: Settings, context: dict[str, Any]) -> StepRecord:
    record = StepRecord(NAME, DESCRIPTION)
    predictions = context["categories"]
    folder = settings.path("labels_dir")
    items, summaries, categories, confusions = [], [], [], []
    for label_set, file_name in LABEL_SETS:
        path = folder / file_name
        if not path.is_file():
            record.metrics[f"{label_set}_labels"] = "missing"
            continue
        try:
            labels = read_label_sheet(path)
        except LabelSheetError as error:
            record.metrics[f"{label_set}_labels"] = f"not scored: {error}"
            continue
        scored = score_items(labels, predictions)
        scored.insert(0, "label_set", label_set)
        items.append(scored)
        summaries.append(summary_rows(scored, label_set))
        categories.append(per_category(scored, label_set))
        confusions.append(confusion(scored, label_set))
        record.metrics[f"{label_set}_labels"] = "scored"
        record.metrics[f"{label_set}_labels_sha256"] = sha256_file(path)
        record.metrics[f"{label_set}_accuracy"] = round(float(scored["correct"].mean()), 4)

    def frame(parts: list[pd.DataFrame], columns: tuple[str, ...] | None = None) -> pd.DataFrame:
        if parts:
            table = pd.concat(parts, ignore_index=True)
            return table[list(columns)] if columns else table
        return pd.DataFrame(columns=list(columns) if columns else ["label_set"])

    processed = settings.path("processed_dir")
    for name, table in (
        ("label_evaluation_items.csv", frame(items, ITEM_COLUMNS)),
        ("label_evaluation_summary.csv", frame(summaries)),
        ("label_evaluation_by_category.csv", frame(categories)),
        ("label_evaluation_confusion.csv", frame(confusions)),
    ):
        path = write_csv(table, processed / name)
        record.outputs.append(describe_output(path, settings.root, rows=len(table)))
    return record
