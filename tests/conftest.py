"""Shared fixtures: a small, self-contained copy of the project.

Tests never touch the real data folders. ``mini_project`` builds a temporary
project with the real configuration file, a six-row raw CSV, and an
``environment.yml`` that pins the versions installed in the test
environment, so the full pipeline and every quality gate run in well under a
second.
"""

from __future__ import annotations

import json
import platform
import shutil
from importlib import metadata
from pathlib import Path

import pytest

from job_market.config import load_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PINNED_FOR_TESTS = ("pandas", "numpy")


def write_local_pins(root: Path) -> None:
    """Pin the versions installed right now, so the environment check passes."""
    python = ".".join(platform.python_version().split(".")[:2])
    lines = ["name: test", "dependencies:", f"  - python={python}"]
    lines += [f"  - {name}={metadata.version(name)}" for name in PINNED_FOR_TESTS]
    # newline="\n" keeps LF line endings on Windows too, so tests that switch
    # the file to CRLF really test the line-ending normalisation.
    (root / "environment.yml").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


START_SOURCE = "from job_market.notebook import start\n\nproject = start()"


def write_notebook(path: Path, cells: list[dict], metadata: dict | None = None) -> None:
    payload = {"cells": cells, "metadata": metadata or {}, "nbformat": 4, "nbformat_minor": 5}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def code_cell(count, text="", error=False, source="x = 1"):
    outputs = [{"output_type": "stream", "name": "stdout", "text": text}] if text else []
    if error:
        outputs.append(
            {"output_type": "error", "ename": "NameError", "evalue": "name 'df' is not defined", "traceback": []}
        )
    return {"cell_type": "code", "execution_count": count, "source": source, "outputs": outputs, "metadata": {}}


def markdown_cell(text):
    return {"cell_type": "markdown", "source": text, "metadata": {}}


def executed_notebook(path: Path, cells: list[dict], run_id: str | None = None) -> dict:
    """Write a notebook the way run-notebooks saves it, with the build run_id in its metadata."""
    metadata = {"job_market": {"run_id": run_id}} if run_id else {}
    notebook = {"cells": cells, "metadata": metadata, "nbformat": 4, "nbformat_minor": 5}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook), encoding="utf-8")
    return notebook


def standard_cells(run_id: str) -> list[dict]:
    return [
        markdown_cell("# 00 Check"),
        code_cell(1, f"RUN_ID: {run_id}\n", source=START_SOURCE),
        code_cell(2, "done\n"),
    ]


def write_executed_notebook(settings, manifest: dict, name: str = "00_check.ipynb") -> Path:
    """A clean notebook run of the given build."""
    path = settings.path("notebooks_dir") / name
    executed_notebook(path, standard_cells(manifest["run_id"]), manifest["run_id"])
    return path


@pytest.fixture
def mini_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("JOB_MARKET_ROOT", raising=False)
    monkeypatch.delenv("JOB_MARKET_STRICT", raising=False)
    (tmp_path / "config").mkdir()
    shutil.copy(REPO_ROOT / "config" / "pipeline.toml", tmp_path / "config" / "pipeline.toml")
    # The mini project carries its own copy of the source code, like a real checkout.
    shutil.copytree(REPO_ROOT / "src", tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    shutil.copytree(REPO_ROOT / "sql", tmp_path / "sql")
    write_local_pins(tmp_path)
    settings = load_settings(tmp_path)
    raw_path = settings.path("raw_csv")
    raw_path.parent.mkdir(parents=True)
    shutil.copy(FIXTURES / "raw_sample.csv", raw_path)
    return settings
