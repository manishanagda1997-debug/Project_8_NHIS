"""Command-line entry point.

    python -m job_market rebuild          rebuild every generated output from the raw CSV
    python -m job_market run-notebooks    execute all notebooks top to bottom in fresh kernels
    python -m job_market check            lineage check: every artifact matches the current build
    python -m job_market check-notebooks  notebook check only (needs the manifest, not the raw data)
    python -m job_market verify           rebuild, run notebooks, then the lineage check

Every command exits with code 0 on success and 1 on failure, so the same
commands work in a terminal, in Docker and in continuous integration.
Set JOB_MARKET_STRICT=1 to turn environment warnings into errors.
"""

from __future__ import annotations

import argparse
import sys

from .config import load_settings
from .qa.findings import Report


def _finish(reports: list[Report], verbose: bool) -> int:
    for report in reports:
        print(report.render(show_ok=verbose))
    return 0 if all(r.passed for r in reports) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m job_market", description="Job-market analysis pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rebuild", help="rebuild every generated output from the raw CSV")
    nb = sub.add_parser("run-notebooks", help="execute notebooks top to bottom in fresh kernels")
    nb.add_argument("--pattern", default="*.ipynb")
    for name, text in (
        ("check", "lineage check"),
        ("check-notebooks", "notebook check only"),
        ("verify", "full rebuild and all checks"),
    ):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("-v", "--verbose", action="store_true", help="also list passing checks")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.command == "rebuild":
        from .pipeline import run_pipeline

        run_pipeline(settings)
        return 0
    if args.command == "run-notebooks":
        from .qa.notebooks import execute_notebooks

        return _finish([execute_notebooks(settings, pattern=args.pattern)], verbose=True)
    if args.command == "check":
        from .qa.lineage import run_lineage_check

        return _finish([run_lineage_check(settings)], args.verbose)
    if args.command == "check-notebooks":
        from .qa.lineage import run_notebook_check

        return _finish([run_notebook_check(settings)], args.verbose)
    if args.command == "verify":
        from .pipeline import run_pipeline
        from .qa.lineage import run_lineage_check
        from .qa.notebooks import execute_notebooks

        run_pipeline(settings)
        notebooks = execute_notebooks(settings)
        return _finish([notebooks, run_lineage_check(settings)], args.verbose)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
