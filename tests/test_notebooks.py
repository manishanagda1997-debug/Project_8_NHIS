"""Notebook evidence: a saved notebook passes only when it is a clean,
error-free, top-to-bottom run of the current build."""

import os

import pytest
from conftest import START_SOURCE, code_cell, executed_notebook, standard_cells, write_notebook

from job_market.qa.lineage import calls_start, notebook_status
from job_market.qa.notebooks import project_notebooks, use_inline_matplotlib_backend

MANIFEST = {"run_id": "run-1"}


def messages(path, manifest=MANIFEST):
    return [message for _, message in notebook_status(path, manifest)]


def saved(tmp_path, cells=None, run_id="run-1"):
    path = tmp_path / "nb.ipynb"
    executed_notebook(path, cells or standard_cells("run-1"), run_id)
    return path


def test_clean_notebook_passes(tmp_path):
    assert messages(saved(tmp_path)) == []


def test_notebook_without_metadata_still_passes_when_outputs_match(tmp_path):
    path = tmp_path / "nb.ipynb"
    write_notebook(path, standard_cells("run-1"))
    assert messages(path) == []


# ------------------------------------------------ order and cell checks


def test_unexecuted_cell_fails(tmp_path):
    cells = [code_cell(1, "RUN_ID: run-1\n", source=START_SOURCE), code_cell(None)]
    assert any("not executed" in m for m in messages(saved(tmp_path, cells=cells)))


def test_out_of_order_execution_fails(tmp_path):
    cells = [code_cell(1, "RUN_ID: run-1\n", source=START_SOURCE), code_cell(5)]
    assert any("execution order" in m for m in messages(saved(tmp_path, cells=cells)))


def test_error_output_fails(tmp_path):
    cells = [code_cell(1, "RUN_ID: run-1\n", source=START_SOURCE, error=True)]
    assert any("NameError" in m for m in messages(saved(tmp_path, cells=cells)))


def test_analysis_before_the_build_check_fails(tmp_path):
    cells = [code_cell(1, "mean rate: 22.5\n"), code_cell(2, "RUN_ID: run-1\n", source=START_SOURCE)]
    found = messages(saved(tmp_path, cells=cells))
    assert any("does not call start()" in m for m in found)
    assert any("does not print the run_id" in m for m in found)


# ------------------------------------------------------------ stale runs


def test_outputs_from_an_older_build_fail(tmp_path):
    path = saved(tmp_path)
    assert any("current build is run-2" in m for m in messages(path, manifest={"run_id": "run-2"}))


def test_stale_run_id_in_a_later_cell_fails(tmp_path):
    cells = [code_cell(1, "RUN_ID: run-1\n", source=START_SOURCE), code_cell(2, "RUN_ID: old\n")]
    assert any("current build" in m for m in messages(saved(tmp_path, cells=cells)))


def test_stale_metadata_run_id_fails(tmp_path):
    path = saved(tmp_path, run_id="run-0")
    assert any("run-0" in m for m in messages(path))


# ------------------------------------------------ recognising start()


@pytest.mark.parametrize(
    "source",
    [
        "from job_market.notebook import start\nproject = start()",
        "from job_market.notebook import start as begin\nproject = begin(verbose=True)",
        "import job_market.notebook as nb\nproject = nb.start()",
        "from job_market import notebook\nproject = notebook.start()",
        "import job_market.notebook\nproject = job_market.notebook.start()",
        "%matplotlib inline\nfrom job_market.notebook import start\nproject = start()",
    ],
)
def test_build_check_calls_are_recognised(source):
    assert calls_start(source)


@pytest.mark.parametrize(
    "source",
    [
        'print("RUN_ID: run-1")',
        "from job_market.notebook import start",
        "def start():\n    pass\nstart()",
        "# from job_market.notebook import start; start()",
        "from job_market.notebook import start\nproject = start",
    ],
)
def test_imitations_of_the_build_check_are_rejected(source):
    assert not calls_start(source)


def test_only_numbered_notebooks_are_project_notebooks(tmp_path):
    for name in ("00_build_overview.ipynb", "01_audit.ipynb", "scratch.ipynb", "Untitled.ipynb", "scratch_02.ipynb"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert [p.name for p in project_notebooks(tmp_path)] == ["00_build_overview.ipynb", "01_audit.ipynb"]


def test_notebook_runner_sets_inline_matplotlib_backend(monkeypatch):
    monkeypatch.delenv("MPLBACKEND", raising=False)
    use_inline_matplotlib_backend()
    assert os.environ["MPLBACKEND"] == "module://matplotlib_inline.backend_inline"
