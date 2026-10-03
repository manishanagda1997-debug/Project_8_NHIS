"""Execute every notebook top to bottom in a fresh kernel.

Each notebook runs in its own new kernel, with the ``notebooks`` folder as the
working directory, and the executed copy replaces the file. A notebook that
raises an error stops the run, and the error stays visible in the saved file.
Hidden state from an earlier interactive session can never leak into the
saved outputs, because nothing survives between kernels.

After a clean run, the notebook metadata records the ``run_id`` of the build
it uses, so the lineage check can detect a notebook from an older build.

Requires the packages ``nbformat``, ``nbclient`` and ``ipykernel``.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Callable

from ..config import Settings, load_settings
from ..manifest import load_manifest
from .findings import ERROR, OK, Report

DEFAULT_TIMEOUT_SECONDS = 1800
METADATA_KEY = "job_market"
# Project notebooks are numbered: 00_build_overview.ipynb, 01_..., 02_...
# Anything else (scratch.ipynb, Untitled.ipynb) is personal and never evidence.
PROJECT_NOTEBOOK = re.compile(r"^\d{2}_[^/\\]+\.ipynb$")


def project_notebooks(folder: Path, pattern: str = "*.ipynb") -> list[Path]:
    """The numbered project notebooks in ``folder``, in order."""
    return sorted(p for p in Path(folder).glob(pattern) if PROJECT_NOTEBOOK.match(p.name))
STANDARD_KERNELSPEC = {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"}


def use_selector_event_loop_on_windows() -> None:
    """Use the event loop that ZeroMQ supports on Windows.

    Jupyter talks to its kernels through ZeroMQ. Python on Windows defaults
    to the "Proactor" event loop, which ZeroMQ does not support: it warns
    ("Proactor event loop does not implement add_reader") and can crash with
    "Assertion failed: pfd.revents & POLLIN". The "Selector" loop avoids both.
    Other systems already use a selector loop, so nothing changes there.
    """
    if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def use_inline_matplotlib_backend() -> None:
    """Make fresh notebook kernels render charts without a desktop GUI backend."""
    os.environ["MPLBACKEND"] = "module://matplotlib_inline.backend_inline"


def execute_notebooks(
    settings: Settings | None = None,
    pattern: str = "*.ipynb",
    kernel_name: str = "python3",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    log: Callable[[str], None] = print,
) -> Report:
    report = Report("Notebook execution")
    try:
        import nbformat
        from nbclient import NotebookClient
    except ImportError as exc:  # pragma: no cover - depends on the environment
        report.add(ERROR, "setup", f"missing package ({exc.name}); install the pinned environment")
        return report

    use_selector_event_loop_on_windows()
    use_inline_matplotlib_backend()
    settings = settings or load_settings()
    try:
        manifest = load_manifest(settings.path("manifest"))
    except (FileNotFoundError, ValueError) as exc:
        report.add(ERROR, "manifest", str(exc))
        return report

    folder = settings.path("notebooks_dir")
    notebooks = project_notebooks(folder, pattern)
    if not notebooks:
        report.add(ERROR, "notebook", f"no numbered notebooks match {pattern} in {settings.relative(folder)}")
        return report

    for path in notebooks:
        location = settings.relative(path)
        log(f"Executing {location} ...")
        notebook = nbformat.read(path, as_version=4)
        notebook.metadata.pop(METADATA_KEY, None)
        client = NotebookClient(
            notebook,
            timeout=timeout,
            kernel_name=kernel_name,
            resources={"metadata": {"path": str(folder)}},
        )
        try:
            notebook = client.execute()
            notebook.metadata[METADATA_KEY] = {"run_id": manifest["run_id"]}
            # The standard kernel name opens on any computer; a personal
            # kernel name such as "jobmarket" exists only on one machine.
            notebook.metadata["kernelspec"] = dict(STANDARD_KERNELSPEC)
            report.add(OK, "notebook", "executes cleanly from a fresh kernel", location)
        except Exception as exc:  # cell error, timeout, dead kernel: all recorded as failures
            lines = str(exc).strip().splitlines()
            report.add(ERROR, "notebook", f"execution stops with an error: {lines[-1] if lines else exc}", location)
        finally:
            nbformat.write(notebook, path)
        if not report.passed:
            break
    return report


__all__ = ["METADATA_KEY", "execute_notebooks", "project_notebooks"]
