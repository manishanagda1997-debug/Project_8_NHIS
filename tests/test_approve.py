"""The approve-recommender command (decision D-040): checks, evidence and a safe write."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from job_market import approve as ap
from job_market import provenance as pv
from job_market.fingerprint import project_code_sha256
from job_market.manifest import MANIFEST_VERSION, describe_output, sha256_file
from job_market.steps.recommend import RELEVANCE_SHEET

ITEMS = pd.DataFrame({"profile_id": ["P01", "P01"], "method": ["tfidf_hybrid", "tfidf_hybrid"], "rank": [1, 2],
                      "row_id": [10, 11], "title_key": ["logo designer", "brand designer"]})


def historical_build(settings, *, source=None, scored=True, items=ITEMS, metrics_extra=None):
    """A build of the historical extract with a completed relevance evaluation."""
    source = source or str(settings.section("labels")["historical_source_sha256"])
    labels = settings.path("labels_dir")
    labels.mkdir(parents=True, exist_ok=True)
    (labels / RELEVANCE_SHEET).write_bytes(b"relevance labels")
    pv.bind_label_sheet(labels, RELEVANCE_SHEET, str(settings.section("labels")["historical_source_sha256"]))
    ITEMS[pv.RANKING_FIELDS].to_csv(labels / "hist.csv", index=False)
    (labels / pv.HISTORICAL_RANKINGS_FILE).write_text(
        f'file = "hist.csv"\nsha256 = "{sha256_file(labels / "hist.csv")}"\n'
        f'source_sha256 = "{settings.section("labels")["historical_source_sha256"]}"\nbuild_id = "H1"\n',
        encoding="utf-8")
    processed = settings.path("processed_dir")
    processed.mkdir(parents=True, exist_ok=True)
    items.to_csv(processed / ap.RELEVANCE_ITEMS, index=False)
    metrics = {"relevance_labels": "scored" if scored else "labels belong to another extract: x",
               "recommend_served_method": "tfidf_hybrid", "recommend_method_status":
               "chosen by the relevance test on this data", "recommend_approval_status": "pending",
               "recommend_winner_mismatch": False}
    if scored:
        metrics.update({"recommend_winner": "tfidf_hybrid", "recommend_winner_reason": "tied; higher strict P@5",
                        "recommend_winner_ndcg_at_5": 0.985, "recommend_historical_rankings": "identical to build H1",
                        "relevance_labels_sha256": sha256_file(labels / RELEVANCE_SHEET)})
    metrics.update(metrics_extra or {})
    manifest = {"manifest_version": MANIFEST_VERSION, "run_id": "R-now",
                "fingerprints": {"code_sha256": project_code_sha256(settings), "config_sha256": settings.config_sha256,
                                 "source_sha256": source},
                "outputs": [describe_output(processed / ap.RELEVANCE_ITEMS, settings.root)],
                "steps": [{"name": "recommend", "metrics": metrics}]}
    settings.path("manifest").write_text(json.dumps(manifest), encoding="utf-8")


def run(settings, answer="yes"):
    lines = []
    code = ap.approve(settings, confirm=lambda _prompt: answer, out=lines.append)
    return code, "\n".join(lines)


def approval_path(settings):
    return settings.root / pv.APPROVAL_FILE


def test_a_checked_historical_build_is_approved_and_loads(mini_project):
    historical_build(mini_project)
    code, text = run(mini_project)
    assert code == 0, text
    record = pv.load_approval(mini_project)
    assert record["approved_method"] == "tfidf_hybrid"
    assert record["evidence"]["build_id"] == "H1"                       # historical build, not the current one
    assert record["evidence"]["rankings_sha256"] == sha256_file(mini_project.path("labels_dir") / "hist.csv")
    assert "Current build:            R-now" in text


def test_cancel_writes_nothing(mini_project):
    historical_build(mini_project)
    code, text = run(mini_project, answer="no")
    assert code == 1 and "Nothing was written" in text
    assert not approval_path(mini_project).exists()


def test_no_build_is_refused(mini_project):
    code, text = run(mini_project)
    assert code == 1 and "no usable build" in text
    assert not approval_path(mini_project).exists()


def test_stale_build_is_refused(mini_project):
    historical_build(mini_project)
    manifest = json.loads(mini_project.path("manifest").read_text(encoding="utf-8"))
    manifest["fingerprints"]["code_sha256"] = "0" * 64
    mini_project.path("manifest").write_text(json.dumps(manifest), encoding="utf-8")
    code, text = run(mini_project)
    assert code == 1 and "stale" in text


def test_valid_labels_without_a_completed_evaluation_are_refused(mini_project):
    historical_build(mini_project, scored=False)
    code, text = run(mini_project)
    assert code == 1 and "no completed relevance evaluation" in text


def test_label_binding_problem_is_refused(mini_project):
    historical_build(mini_project)
    (mini_project.path("labels_dir") / RELEVANCE_SHEET).write_bytes(b"edited after binding")
    code, text = run(mini_project)
    assert code == 1 and "not usable for this extract" in text


def test_other_extract_is_refused(mini_project):
    historical_build(mini_project, source="e" * 64)
    code, text = run(mini_project)
    assert code == 1 and "not the historical evaluation extract" in text


def test_different_rankings_are_refused_even_if_the_build_says_identical(mini_project):
    historical_build(mini_project, items=ITEMS.assign(row_id=[10, 99]))
    code, text = run(mini_project)
    assert code == 1 and "rankings differ" in text


def test_evidence_hash_mismatch_is_refused(mini_project):
    historical_build(mini_project, metrics_extra={"relevance_labels_sha256": "f" * 64})
    code, text = run(mini_project)
    assert code == 1 and "differs from the one this build scored" in text


def test_existing_approval_is_never_replaced(mini_project):
    historical_build(mini_project)
    approval_path(mini_project).write_text("existing", encoding="utf-8")
    code, text = run(mini_project)
    assert code == 1 and "never replaced" in text
    assert approval_path(mini_project).read_text(encoding="utf-8") == "existing"


def test_changes_after_the_summary_stop_the_write(mini_project):
    historical_build(mini_project)

    def edit_then_yes(_prompt):
        (mini_project.path("labels_dir") / pv.LABEL_SOURCES_FILE).write_text(
            (mini_project.path("labels_dir") / pv.LABEL_SOURCES_FILE).read_text(encoding="utf-8") + "\n# edited\n",
            encoding="utf-8")
        return "yes"

    lines = []
    code = ap.approve(mini_project, confirm=edit_then_yes, out=lines.append)
    assert code == 1 and "changed after the summary" in "\n".join(lines)
    assert not approval_path(mini_project).exists()


def test_approval_appearing_after_the_summary_is_not_replaced(mini_project):
    historical_build(mini_project)

    def create_then_yes(_prompt):
        approval_path(mini_project).write_text("someone else", encoding="utf-8")
        return "yes"

    lines = []
    code = ap.approve(mini_project, confirm=create_then_yes, out=lines.append)
    assert code == 1 and "never replaced" in "\n".join(lines)
    assert approval_path(mini_project).read_text(encoding="utf-8") == "someone else"


def test_an_unreadable_written_approval_is_removed(mini_project, monkeypatch):
    historical_build(mini_project)
    monkeypatch.setattr(pv, "approval_text", lambda *args: "approved_method = 1\n")
    code, text = run(mini_project)
    assert code == 1 and "was removed" in text
    assert not approval_path(mini_project).exists()
