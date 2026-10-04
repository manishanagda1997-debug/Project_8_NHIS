"""Scoring against human labels (decisions D-027 and D-029)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from job_market.evaluate import confusion, per_category, rules_only, score_items, summary_rows, wilson_interval
from job_market.taxonomy import OTHER


def test_wilson_interval_known_values():
    low, high = wilson_interval(241, 350)
    assert (round(low, 3), round(high, 3)) == (0.638, 0.735)
    assert wilson_interval(0, 10)[0] == 0.0          # never below 0
    assert wilson_interval(10, 10)[1] == 1.0         # never above 1
    assert all(math.isnan(v) for v in wilson_interval(0, 0))


def predictions():
    return pd.DataFrame(
        {
            "row_id": [1, 2, 3, 4],
            "primary_category": ["web_development", "design_creative", OTHER, "writing_content"],
            "category_method": ["rule", "tfidf_classifier", "below_threshold", "rule"],
            "rule_score": [6, 0, 0, 3],
            "classifier_category": ["web_development", "design_creative", "legal", "writing_content"],
            "classifier_probability": [0.9, 0.8, 0.3, 0.6],
            "matched_terms": ["website", "", "", "writer"],
        }
    )


def labels():
    return pd.DataFrame(
        {
            "sample_id": ["B001", "B002", "B003", "B004"],
            "row_id": [1, 2, 3, 4],
            "title": ["a", "b", "c", "d"],
            "category": ["web_development", "design_creative", "legal", "video_animation"],
            "unsure": [False, False, True, False],
            "note": [None, None, "hard", None],
        }
    )


def test_score_items_marks_correct_and_rules_only():
    items = score_items(labels(), predictions())
    assert items["correct"].tolist() == [True, True, False, False]
    # Without the classifier, the design guess becomes Other.
    assert items["rules_only"].tolist() == ["web_development", OTHER, OTHER, "writing_content"]
    assert items["correct_rules_only"].tolist() == [True, False, False, False]


def test_score_items_refuses_labels_without_prediction():
    with pytest.raises(ValueError, match="without a prediction"):
        score_items(labels().assign(row_id=[1, 2, 3, 99]), predictions())


def test_summary_rows():
    table = summary_rows(score_items(labels(), predictions()), "blind").set_index(["subset", "system"])
    assert table.loc[("all", "full"), "accuracy"] == 0.5
    assert table.loc[("all", "rules_only"), "accuracy"] == 0.25
    assert table.loc[("labelled_unsure", "full"), "titles"] == 1
    assert table.loc[("predicted_not_other", "full"), "titles"] == 3
    assert table.loc[("all", "full"), "wilson_low"] < 0.5 < table.loc[("all", "full"), "wilson_high"]


def test_per_category_precision_recall():
    table = per_category(score_items(labels(), predictions()), "blind").set_index("category")
    assert table.loc["writing_content", "precision"] == 0.0     # predicted once, wrong
    assert table.loc["video_animation", "recall"] == 0.0        # labelled once, missed
    assert table.loc["web_development", "f1"] == 1.0
    assert table.loc["legal", "human_titles"] == 1 and table.loc["legal", "predicted_titles"] == 0


def test_confusion_counts_add_up():
    table = confusion(score_items(labels(), predictions()), "blind")
    assert table["titles"].sum() == 4
    assert ((table["human"] == "legal") & (table["predicted"] == OTHER)).any()


def test_rules_only_keeps_rule_decisions():
    assert rules_only(predictions()).tolist() == ["web_development", OTHER, OTHER, "writing_content"]


def test_build_scores_complete_label_sheets_and_skips_others(mini_project):
    """End to end: a filled-in development sheet is scored, a missing blind sheet is skipped."""
    from openpyxl import load_workbook

    from job_market.labels import write_label_sheet
    from job_market.pipeline import run_pipeline

    folder = mini_project.path("labels_dir")
    folder.mkdir(parents=True, exist_ok=True)
    sheet = folder / "dev_labels.xlsx"
    sample = pd.DataFrame({"sample_id": ["D001", "D002"], "row_id": [1, 3], "title": ["Logo designer", "Virtual assistant"]})
    write_label_sheet(sample, sheet)
    book = load_workbook(sheet)
    book["labels"]["D2"] = "design_creative"
    book["labels"]["D3"] = "admin_virtual_assistance"
    book.save(sheet)

    manifest = run_pipeline(mini_project, log=lambda _: None)
    metrics = {step["name"]: step["metrics"] for step in manifest["steps"]}["evaluate"]
    assert metrics["dev_labels"] == "scored"
    assert metrics["blind_labels"] == "missing"
    assert metrics["dev_accuracy"] == 1.0
    summary = pd.read_csv(mini_project.path("processed_dir") / "label_evaluation_summary.csv")
    assert set(summary["label_set"]) == {"dev"}
