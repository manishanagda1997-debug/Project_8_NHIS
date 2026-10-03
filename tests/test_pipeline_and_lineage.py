"""End-to-end tests: build the mini project, then prove the lineage check
catches every kind of stale or tampered artifact."""

import pytest
from conftest import write_executed_notebook

from job_market.environment import EnvironmentMismatchError
from job_market.manifest import load_manifest
from job_market.pipeline import run_pipeline
from job_market.qa.lineage import run_lineage_check


def quiet(_message):
    return None


def build(settings, with_notebook=True):
    manifest = run_pipeline(settings, log=quiet)
    if with_notebook:
        write_executed_notebook(settings, manifest)
    return manifest


def test_build_writes_manifest_with_counts_and_hashes(mini_project):
    manifest = build(mini_project)
    stored = load_manifest(mini_project.path("manifest"))
    assert stored["run_id"] == manifest["run_id"]
    assert stored["counts"]["raw_rows"] == 6
    assert stored["counts"]["missing_title"] == 1
    assert stored["source"]["rows"] == 6
    assert all(len(entry["sha256"]) == 64 for entry in stored["outputs"])


def test_manifest_records_every_pinned_package(mini_project):
    manifest = build(mini_project)
    assert set(manifest["environment"]["packages"]) == {"pandas", "numpy"}


def test_rebuild_is_byte_identical(mini_project):
    first = {e["path"]: e["sha256"] for e in build(mini_project)["outputs"]}
    second = {e["path"]: e["sha256"] for e in build(mini_project)["outputs"]}
    assert first == second


def test_fresh_build_passes_the_lineage_check(mini_project):
    build(mini_project)
    report = run_lineage_check(mini_project)
    assert report.passed, report.render()


def test_lineage_check_is_strict_only_in_strict_mode(mini_project, monkeypatch):
    build(mini_project)
    assert not run_lineage_check(mini_project).strict
    monkeypatch.setenv("JOB_MARKET_STRICT", "1")
    assert run_lineage_check(mini_project).strict


def test_tampered_output_fails(mini_project):
    manifest = build(mini_project)
    target = mini_project.root / manifest["outputs"][0]["path"]
    target.write_text(target.read_text(encoding="utf-8") + "extra\n", encoding="utf-8")
    report = run_lineage_check(mini_project)
    assert not report.passed
    assert any("differs from the manifest hash" in f.message for f in report.errors)


def test_missing_output_fails(mini_project):
    manifest = build(mini_project)
    (mini_project.root / manifest["outputs"][0]["path"]).unlink()
    assert not run_lineage_check(mini_project).passed


def test_leftover_file_fails(mini_project):
    build(mini_project)
    (mini_project.path("processed_dir") / "old_result.csv").write_text("a\n1\n", encoding="utf-8")
    report = run_lineage_check(mini_project)
    assert any(f.check == "untracked" for f in report.errors)


def test_rebuild_removes_leftover_files(mini_project):
    build(mini_project)
    leftover = mini_project.path("processed_dir") / "old_result.csv"
    leftover.write_text("a\n1\n", encoding="utf-8")
    build(mini_project)
    assert not leftover.exists()


def test_changed_raw_data_marks_the_build_stale(mini_project):
    build(mini_project)
    raw = mini_project.path("raw_csv")
    raw.write_text(
        raw.read_text(encoding="utf-8")
        + "Extra job,https://example.com/z,2024-03-04 10:00:00+00:00,True,10,20,,India\n",
        encoding="utf-8",
    )
    report = run_lineage_check(mini_project)
    assert any(f.check == "fingerprint" and "raw data" in f.message for f in report.errors)


def test_missing_manifest_fails_cleanly(mini_project):
    report = run_lineage_check(mini_project)
    assert not report.passed
    assert "rebuild" in report.errors[0].message


def test_no_notebooks_fails(mini_project):
    build(mini_project, with_notebook=False)
    report = run_lineage_check(mini_project)
    assert any(f.check == "notebook" and "no notebooks" in f.message for f in report.errors)


def unpin_pandas(settings):
    pins = settings.root / "environment.yml"
    pins.write_text(pins.read_text(encoding="utf-8").replace("- pandas=", "- pandas=0.0.1-"), encoding="utf-8")


def test_build_in_another_environment_warns_and_records_it(mini_project):
    unpin_pandas(mini_project)
    manifest = build(mini_project)
    assert manifest["environment_matches_pins"] is False
    report = run_lineage_check(mini_project)
    assert report.passed, report.render()
    assert any(f.check == "environment" and "pandas" in f.message for f in report.warnings)


def test_strict_build_in_another_environment_is_refused(mini_project, monkeypatch):
    unpin_pandas(mini_project)
    monkeypatch.setenv("JOB_MARKET_STRICT", "1")
    with pytest.raises(EnvironmentMismatchError, match="pandas"):
        run_pipeline(mini_project, log=quiet)
    assert not mini_project.path("manifest").exists()


def test_notebook_check_needs_no_raw_data(mini_project):
    from job_market.qa.lineage import run_notebook_check

    build(mini_project)
    mini_project.path("raw_csv").unlink()
    report = run_notebook_check(mini_project)
    assert report.passed, report.render()


def test_build_without_an_environment_file_is_refused(mini_project):
    (mini_project.root / "environment.yml").unlink()
    with pytest.raises(EnvironmentMismatchError, match="missing"):
        run_pipeline(mini_project, log=quiet)
