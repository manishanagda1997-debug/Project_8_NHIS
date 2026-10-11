"""Environment pins warn by default and fail in strict mode; the build always
uses this project's own code."""

import json

import pytest
from conftest import write_executed_notebook

from job_market.environment import EnvironmentMismatchError, version_matches
from job_market.fingerprint import InstalledPackageMismatchError, current_fingerprints, verify_installed_package
from job_market.notebook import start
from job_market.pipeline import run_pipeline
from job_market.qa.lineage import run_lineage_check


def quiet(_message):
    return None


# ------------------------------------------------------ exact version pins


@pytest.mark.parametrize(
    "package, pinned, installed, expected",
    [
        ("python", "3.11", "3.11.9", True),
        ("python", "3.11", "3.11.0", True),
        ("python", "3.11", "3.12.0", False),
        ("python", "3.11", "3.1", False),
        ("python", "3.11", "3.110.1", False),
        ("pandas", "2.2.3", "2.2.3", True),
        ("pandas", "2.2.3", "2.2.4", False),
        ("pandas", "2.2.3", "2.2.3.post1", False),
        ("pandas", "2.2.3", "2.2.3.1", False),
        ("pandas", "2.2.3", None, False),
    ],
)
def test_version_matching(package, pinned, installed, expected):
    assert version_matches(package, pinned, installed) is expected


# ------------------------------------------- build environment before use


@pytest.fixture
def built(mini_project, monkeypatch):
    manifest = run_pipeline(mini_project, log=quiet)
    write_executed_notebook(mini_project, manifest)
    monkeypatch.chdir(mini_project.path("notebooks_dir"))
    return mini_project


def set_manifest_pandas(settings, version):
    path = settings.path("manifest")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["environment"]["packages"]["pandas"] = version
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_start_warns_about_outputs_built_in_another_environment(built, capsys):
    set_manifest_pandas(built, "0.0.1")
    start()
    out = capsys.readouterr().out
    assert "ENVIRONMENT WARNING" in out
    assert "pandas" in out


def test_strict_start_refuses_outputs_built_in_another_environment(built, monkeypatch):
    set_manifest_pandas(built, "0.0.1")
    monkeypatch.setenv("JOB_MARKET_STRICT", "1")
    with pytest.raises(EnvironmentMismatchError, match="builds these outputs"):
        start(verbose=False)


def test_start_accepts_a_pinned_build(built):
    assert start(verbose=False).run_id


# ------------------------------------------------- this project's code


def test_code_fingerprint_follows_this_project_source(mini_project):
    before = current_fingerprints(mini_project)["code_sha256"]
    cli = mini_project.root / "src" / "job_market" / "cli.py"
    cli.write_text(cli.read_text(encoding="utf-8") + "\n# local change\n", encoding="utf-8")
    assert current_fingerprints(mini_project)["code_sha256"] != before


def test_label_fingerprint_covers_exactly_the_pipeline_label_inputs(mini_project):
    from job_market import provenance
    from job_market.fingerprint import LABEL_INPUT_FILES, labels_sha256
    from job_market.steps.evaluate import LABEL_SETS
    from job_market.steps.recommend import RELEVANCE_SHEET

    assert set(LABEL_INPUT_FILES) == {name for _, name in LABEL_SETS} | {
        RELEVANCE_SHEET, provenance.LABEL_SOURCES_FILE, provenance.HISTORICAL_RANKINGS_FILE}
    folder = mini_project.path("labels_dir")
    folder.mkdir(parents=True, exist_ok=True)
    empty = labels_sha256(mini_project)
    assert labels_sha256(mini_project) == empty                       # missing files give a stable value
    seen = {empty}
    for name in LABEL_INPUT_FILES:                                      # adding each file changes it ...
        (folder / name).write_text(f'file = "hist.csv"\n# {name}\n' if name == provenance.HISTORICAL_RANKINGS_FILE
                                   else name, encoding="utf-8")
        seen.add(labels_sha256(mini_project))
    (folder / "hist.csv").write_text("rankings", encoding="utf-8")     # ... and so does the file the record names
    seen.add(labels_sha256(mini_project))
    (folder / "dev_labels.xlsx").write_text("edited", encoding="utf-8")  # ... and so does an edit
    seen.add(labels_sha256(mini_project))
    assert len(seen) == len(LABEL_INPUT_FILES) + 3
    before = labels_sha256(mini_project)
    (folder / "arrangement_eval.xlsx").write_text("not a pipeline input", encoding="utf-8")
    approval = mini_project.root / provenance.APPROVAL_FILE
    approval.write_text("approved_method = 'x'\n", encoding="utf-8")
    assert labels_sha256(mini_project) == before                       # arrangement sheets and approval excluded


def test_editing_a_label_file_after_the_build_makes_it_stale(mini_project):
    from job_market.qa.findings import ERROR

    manifest = run_pipeline(mini_project, log=quiet)
    folder = mini_project.path("labels_dir")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "blind_labels.xlsx").write_text("labels added after the build", encoding="utf-8")
    report = run_lineage_check(mini_project)
    assert manifest["fingerprints"]["labels_sha256"]
    assert any(f.level == ERROR and "label files (data/labels) differs from the build" in f.message
               for f in report.findings)


def test_copied_project_with_changed_code_needs_reinstall(mini_project):
    verify_installed_package(mini_project)  # identical copy: accepted
    cli = mini_project.root / "src" / "job_market" / "cli.py"
    cli.write_text(cli.read_text(encoding="utf-8") + "\n# local change\n", encoding="utf-8")
    with pytest.raises(InstalledPackageMismatchError, match="pip install -e"):
        verify_installed_package(mini_project)


def test_build_refuses_code_that_is_not_installed(mini_project):
    cli = mini_project.root / "src" / "job_market" / "cli.py"
    cli.write_text(cli.read_text(encoding="utf-8") + "\n# local change\n", encoding="utf-8")
    with pytest.raises(InstalledPackageMismatchError):
        run_pipeline(mini_project, log=quiet)


def test_check_reports_code_that_is_not_installed(built):
    cli = built.root / "src" / "job_market" / "cli.py"
    cli.write_text(cli.read_text(encoding="utf-8") + "\n# local change\n", encoding="utf-8")
    report = run_lineage_check(built)
    assert any("pip install -e" in f.message for f in report.errors)
    with pytest.raises(InstalledPackageMismatchError):
        start(verbose=False)
