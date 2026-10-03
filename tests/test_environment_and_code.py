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
