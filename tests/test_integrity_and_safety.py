"""Safety and integrity guarantees: nothing destroys source data, nothing
reads a tampered output, and Git keeps hashed files byte-identical."""

import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest
from conftest import REPO_ROOT, write_executed_notebook

from job_market.config import LayoutError, load_settings
from job_market.manifest import IntegrityError
from job_market.notebook import StaleBuildError, start
from job_market.pipeline import run_pipeline
from job_market.qa.notebooks import project_notebooks
from job_market.steps.ingest import SchemaError, parse_timestamps, require_timestamps


def quiet(_message):
    return None


def set_path(settings, key, value):
    config = settings.root / "config" / "pipeline.toml"
    lines = config.read_text(encoding="utf-8").splitlines()
    replaced = [f'{key} = "{value}"' if line.startswith(f"{key} = ") else line for line in lines]
    config.write_text("\n".join(replaced) + "\n", encoding="utf-8")


# ------------------------------------------------------ destructive paths


@pytest.mark.parametrize(
    "key, value",
    [
        ("processed_dir", "data/raw"),
        ("processed_dir", "data"),
        ("processed_dir", "."),
        ("interim_dir", "config"),
        ("interim_dir", "src"),
        ("processed_dir", "notebooks"),
        ("interim_dir", "tests"),
        ("processed_dir", "docs"),
        ("interim_dir", "data/processed"),
        ("processed_dir", "../outside"),
    ],
)
def test_unsafe_generated_folder_is_refused(mini_project, key, value):
    set_path(mini_project, key, value)
    with pytest.raises(LayoutError):
        load_settings(mini_project.root)


def test_unsafe_configuration_deletes_nothing(mini_project):
    raw = mini_project.path("raw_csv")
    before = raw.read_bytes()
    set_path(mini_project, "processed_dir", "data/raw")
    with pytest.raises(LayoutError):
        run_pipeline(load_settings(mini_project.root), log=quiet)
    assert raw.read_bytes() == before


def test_manifest_outside_processed_folder_is_refused(mini_project):
    set_path(mini_project, "manifest", "data/run_manifest.json")
    with pytest.raises(LayoutError, match="manifest"):
        load_settings(mini_project.root)


# ------------------------------------------------ notebook read integrity


@pytest.fixture
def built(mini_project, monkeypatch):
    manifest = run_pipeline(mini_project, log=quiet)
    write_executed_notebook(mini_project, manifest)
    monkeypatch.chdir(mini_project.path("notebooks_dir"))
    return mini_project


def test_start_prints_the_run_id(built, capsys):
    project = start()
    assert f"RUN_ID: {project.run_id}" in capsys.readouterr().out


def test_start_refuses_a_tampered_output(built):
    target = built.path("processed_dir") / "raw_column_profile.csv"
    target.write_text(target.read_text(encoding="utf-8").replace("title", "TITLE"), encoding="utf-8")
    with pytest.raises(IntegrityError, match="raw_column_profile.csv"):
        start(verbose=False)


def test_read_csv_refuses_a_file_changed_after_start(built):
    project = start(verbose=False)
    target = built.path("processed_dir") / "raw_column_profile.csv"
    target.write_text(target.read_text(encoding="utf-8") + "fake,row\n", encoding="utf-8")
    with pytest.raises(IntegrityError):
        project.read_csv("raw_column_profile.csv")


def test_read_csv_returns_verified_data(built):
    frame = start(verbose=False).read_csv("raw_column_profile.csv")
    assert isinstance(frame, pd.DataFrame)
    assert "title" in set(frame["column"])


def test_read_csv_refuses_a_file_outside_the_build(built):
    with pytest.raises(FileNotFoundError):
        start(verbose=False).read_csv("not_an_output.csv")


def test_start_refuses_a_stale_build(built):
    config = built.root / "config" / "pipeline.toml"
    config.write_text(config.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    with pytest.raises(StaleBuildError):
        start(verbose=False)


# ----------------------------------------------------------- timestamps


def test_file_without_any_valid_timestamp_fails_clearly():
    with pytest.raises(SchemaError, match="no parseable timestamps"):
        require_timestamps(parse_timestamps(pd.Series(["soon", "later"])))


def test_pipeline_reports_invalid_timestamps_clearly(mini_project):
    raw = mini_project.path("raw_csv")
    frame = pd.read_csv(raw, keep_default_na=False, na_values=[""], dtype=str)
    frame["published_date"] = "not a date"
    frame.to_csv(raw, index=False)
    with pytest.raises(SchemaError, match="no parseable timestamps"):
        run_pipeline(mini_project, log=quiet)


# ---------------------------------------------------------------- Git


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_git_keeps_hashed_files_byte_identical(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    shutil.copy(REPO_ROOT / ".gitattributes", tmp_path / ".gitattributes")
    result = subprocess.run(
        ["git", "check-attr", "text", "--", "data/raw/a.csv", "data/processed/b.csv", "README.md"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    attributes = dict(line.rsplit(": ", 1) for line in result.stdout.strip().splitlines())
    assert attributes["data/raw/a.csv: text"] == "unset"
    assert attributes["data/processed/b.csv: text"] == "unset"
    assert attributes["README.md: text"] == "auto"


# --------------------------------------------------- notebook execution


def run_real_notebook(built, cells_source):
    """Execute one notebook in a real Jupyter kernel and return (report, saved notebook JSON)."""
    import json

    nbformat = pytest.importorskip("nbformat")
    pytest.importorskip("nbclient")
    pytest.importorskip("ipykernel")
    from job_market.qa.notebooks import execute_notebooks

    folder = built.path("notebooks_dir")
    for old in folder.glob("*.ipynb"):
        old.unlink()
    notebook = nbformat.v4.new_notebook()
    notebook.cells = [nbformat.v4.new_markdown_cell("# 01 Demo")]
    notebook.cells += [nbformat.v4.new_code_cell(source) for source in cells_source]
    path = folder / "01_demo.ipynb"
    nbformat.write(notebook, path)
    env_backup = os.environ.get("JOB_MARKET_ROOT")
    os.environ["JOB_MARKET_ROOT"] = str(built.root)
    try:
        report = execute_notebooks(built, log=quiet)
    finally:
        if env_backup is None:
            os.environ.pop("JOB_MARKET_ROOT", None)
        else:
            os.environ["JOB_MARKET_ROOT"] = env_backup
    return report, json.loads(path.read_text(encoding="utf-8"))


def test_real_kernel_runs_a_correct_notebook(built):
    """Real Jupyter kernel: a correct notebook runs cleanly, keeps exactly its
    own cells, records the build run_id and passes the lineage check."""
    from job_market.qa.lineage import run_lineage_check

    sources = ["from job_market.notebook import start\nproject = start()", "print(project.counts['raw_rows'])"]
    report, saved = run_real_notebook(built, sources)
    assert report.passed, report.render()

    code = [c for c in saved["cells"] if c["cell_type"] == "code"]
    assert ["".join(c["source"]) for c in code] == sources
    assert [c["execution_count"] for c in code] == [1, 2]
    from job_market.manifest import load_manifest

    assert saved["metadata"]["job_market"]["run_id"] == load_manifest(built.path("manifest"))["run_id"]
    assert run_lineage_check(built).passed, run_lineage_check(built).render()


def test_real_kernel_rejects_start_in_the_second_cell(built):
    """Real Jupyter kernel: analysis first and start() second executes, but the
    lineage check fails it, because the first code cell does not verify the build."""
    from job_market.qa.lineage import run_lineage_check

    sources = ["x = 1 + 1", "from job_market.notebook import start\nproject = start()"]
    report, _saved = run_real_notebook(built, sources)
    assert report.passed, report.render()
    messages = [f.message for f in run_lineage_check(built).errors]
    assert any("does not call start()" in m for m in messages)


def test_repo_notebooks_start_with_the_build_check():
    # Every committed notebook's first code cell must call start().
    import json

    for path in project_notebooks(REPO_ROOT / "notebooks"):
        cells = json.loads(Path(path).read_text(encoding="utf-8"))["cells"]
        first_code = next(c for c in cells if c["cell_type"] == "code")
        assert "start()" in "".join(first_code["source"]), path.name


HEADER_FIELDS = ("Purpose", "Assignment requirement", "Inputs", "Outputs", "Build identity")


def test_repo_notebooks_open_with_the_standard_header():
    import json

    for path in project_notebooks(REPO_ROOT / "notebooks"):
        first = json.loads(Path(path).read_text(encoding="utf-8"))["cells"][0]
        text = "".join(first["source"])
        assert first["cell_type"] == "markdown", path.name
        assert text.startswith(f"# {path.name[:2]} "), path.name
        for field in HEADER_FIELDS:
            assert f"**{field}**" in text, f"{path.name} lacks header field {field}"


# ------------------------------------------- configured protected paths


@pytest.mark.parametrize(
    "key, value",
    [
        ("reports_dir", "data/processed/reports"),
        ("reports_dir", "data/interim"),
        ("notebooks_dir", "data/processed/notebooks"),
        ("raw_csv", "data/processed/raw.csv"),
        ("raw_csv", "raw.csv"),
        ("reports_dir", "../elsewhere"),
        ("manifest", "../manifest.json"),
    ],
)
def test_configured_paths_are_validated(mini_project, key, value):
    set_path(mini_project, key, value)
    with pytest.raises(LayoutError):
        load_settings(mini_project.root)


# ------------------------------------------------ environment integrity


def test_changing_the_pinned_environment_marks_the_build_stale(built):
    from job_market.qa.lineage import run_lineage_check

    pins = built.root / "environment.yml"
    pins.write_text(pins.read_text(encoding="utf-8") + "# note\n", encoding="utf-8")
    report = run_lineage_check(built)
    assert any(f.check == "fingerprint" and "pinned environment" in f.message for f in report.errors)
    with pytest.raises(StaleBuildError, match="pinned environment"):
        start(verbose=False)


def test_environment_fingerprint_ignores_line_endings(built):
    from job_market.qa.lineage import run_lineage_check

    pins = built.root / "environment.yml"
    pins.write_bytes(pins.read_bytes().replace(b"\n", b"\r\n"))
    assert run_lineage_check(built).passed


@pytest.fixture
def different_pandas(monkeypatch):
    import job_market.environment as environment

    real = environment.installed_version
    monkeypatch.setattr(environment, "installed_version", lambda name: "0.0.1" if name == "pandas" else real(name))


def test_check_warns_when_the_running_environment_differs(built, different_pandas):
    from job_market.qa.lineage import run_lineage_check

    report = run_lineage_check(built)
    assert report.passed, report.render()
    assert any(f.check == "environment" and "running environment" in f.message for f in report.warnings)
    # The recorded build environment itself still matches: two separate checks.
    assert not any("the build uses" in f.message for f in report.warnings)


def test_strict_check_fails_when_the_running_environment_differs(built, different_pandas, monkeypatch):
    from job_market.qa.lineage import run_lineage_check

    monkeypatch.setenv("JOB_MARKET_STRICT", "1")
    report = run_lineage_check(built)
    assert not report.passed
    assert any(f.check == "environment" and "running environment" in f.message for f in report.errors)


def test_start_warns_in_another_environment(built, different_pandas, capsys):
    start()
    assert "ENVIRONMENT WARNING" in capsys.readouterr().out


def test_strict_start_refuses_another_environment(built, different_pandas, monkeypatch):
    from job_market.notebook import EnvironmentMismatchError

    monkeypatch.setenv("JOB_MARKET_STRICT", "1")
    with pytest.raises(EnvironmentMismatchError, match="pandas"):
        start(verbose=False)


# ------------------------------------------------------------ robustness


def test_missing_raw_file_is_a_finding_not_a_crash(built):
    from job_market.qa.lineage import run_lineage_check

    built.path("raw_csv").unlink()
    report = run_lineage_check(built)
    assert not report.passed
    assert any("raw file" in f.message and "missing" in f.message for f in report.errors)
