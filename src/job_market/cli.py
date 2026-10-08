"""Command-line entry point.

    python -m job_market rebuild          rebuild every generated output from the raw CSV
    python -m job_market run-notebooks    execute all notebooks top to bottom in fresh kernels
    python -m job_market check            lineage check: every artifact matches the current build
    python -m job_market check-notebooks  notebook check only (needs the manifest, not the raw data)
    python -m job_market verify           rebuild, run notebooks, then the lineage check
    python -m job_market make-label-sheets  draw the blind and development samples as Excel sheets (once)
    python -m job_market make-relevance-sheet  write the blinded recommendation relevance sheet (once)
    python -m job_market make-arrangement-pilot  write the 30-title work-arrangement pilot sheet (once)
    python -m job_market make-arrangement-dev  write the remaining development titles after the pilot (once)
    python -m job_market serve            start the web app (recommendations and API) on http://127.0.0.1:5000

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
    sub.add_parser("make-label-sheets", help="draw the label samples and write the Excel sheets (refuses to overwrite)")
    sub.add_parser("make-relevance-sheet", help="write the blinded relevance sheet for the recommender (refuses to overwrite)")
    sub.add_parser("make-arrangement-pilot",
                   help="write the 30-title work-arrangement pilot sheet and its selection record (refuses to overwrite)")
    sub.add_parser("make-arrangement-dev",
                   help="write the remaining development titles (after the pilot) and their record (refuses to overwrite)")
    serve = sub.add_parser("serve", help="start the web app on http://127.0.0.1:5000")
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on (0.0.0.0 inside Docker)")
    serve.add_argument("--port", type=int, default=5000)
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
    if args.command == "make-arrangement-pilot":
        import json

        import pandas as pd

        from .arrangement import GUIDE, development_sample, selection_record, title_frame, write_arrangement_sheet
        from .manifest import load_manifest, sha256_file, verify_output

        manifest = load_manifest(settings.path("manifest"))
        entry = next(o for o in manifest["outputs"] if o["path"].endswith("jobs_clean.parquet"))
        jobs_path = verify_output(entry, settings.root)        # the bytes recorded by the build, or stop
        folder = settings.path("labels_dir")
        sheet, record_path = folder / "arrangement_dev_pilot.xlsx", folder / "arrangement_dev_selection.json"
        if sheet.exists() or record_path.exists():
            print("refusing to overwrite an existing pilot sheet or selection record")
            return 1
        rules = settings.section("arrangement")
        jobs = pd.read_parquet(jobs_path, columns=["row_id", "title_key", "title_clean", "eligible_for_timeseries"])
        sample, summary = development_sample(title_frame(jobs), rules)
        record = selection_record(sample, summary, rules, manifest["fingerprints"]["source_sha256"], entry["sha256"],
                                  sha256_file(settings.root / GUIDE))
        record["pilot_sheet"] = settings.relative(sheet)
        write_arrangement_sheet(sample[sample["pilot"]], sheet)
        record["pilot_sheet_sha256_at_creation"] = sha256_file(sheet)
        record_path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {settings.relative(sheet)}: {int(sample['pilot'].sum())} titles")
        print(f"wrote {settings.relative(record_path)}: design, counts and hashes (no per-title groups)")
        return 0
    if args.command == "make-arrangement-dev":
        import json

        import pandas as pd
        from openpyxl import load_workbook

        from .arrangement import GUIDE, development_sample, title_frame, write_arrangement_sheet
        from .manifest import load_manifest, sha256_file, verify_output

        manifest = load_manifest(settings.path("manifest"))
        entry = next(o for o in manifest["outputs"] if o["path"].endswith("jobs_clean.parquet"))
        jobs_path = verify_output(entry, settings.root)
        folder = settings.path("labels_dir")
        pilot_path = folder / "arrangement_dev_pilot.xlsx"
        sheet, record_path = folder / "arrangement_dev_main.xlsx", folder / "arrangement_dev_main_selection.json"
        if sheet.exists() or record_path.exists():
            print("refusing to overwrite an existing development sheet or record")
            return 1
        rules = settings.section("arrangement")
        jobs = pd.read_parquet(jobs_path, columns=["row_id", "title_key", "title_clean", "eligible_for_timeseries"])
        sample, _ = development_sample(title_frame(jobs), rules)
        # The pilot sheet must still hold exactly the pilot part of this sample.
        pilot_rows = [(r[0], r[1]) for r in load_workbook(pilot_path)["labels"].iter_rows(min_row=2, values_only=True)]
        expected = list(sample.loc[sample["pilot"], ["sample_id", "title"]].itertuples(index=False, name=None))
        if pilot_rows != expected:
            print("the pilot sheet does not match the pilot part of the development sample; stopping")
            return 1
        rest = sample[~sample["pilot"]]
        write_arrangement_sheet(rest, sheet)
        record = {"decision": "D-041", "stage": "development (after the pilot)",
                  "source_sha256": manifest["fingerprints"]["source_sha256"], "jobs_clean_sha256": entry["sha256"],
                  "guide_sha256": sha256_file(settings.root / GUIDE), "seed": int(rules["seed"]),
                  "titles": int(len(rest)), "first_sample_id": rest["sample_id"].iloc[0],
                  "last_sample_id": rest["sample_id"].iloc[-1], "sheet": settings.relative(sheet),
                  "sheet_sha256_at_creation": sha256_file(sheet)}
        record_path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {settings.relative(sheet)}: {len(rest)} titles ({record['first_sample_id']} to {record['last_sample_id']})")
        print(f"wrote {settings.relative(record_path)}")
        return 0
    if args.command == "make-label-sheets":
        from .labels import draw_samples, write_label_sheet
        from .notebook import start

        project = start(verbose=False)
        frame = project.read_parquet(
            "jobs_clean.parquet", columns=["row_id", "title_clean", "title_key", "title_word_count", "eligible_for_text_analysis"]
        )
        blind, dev = draw_samples(frame, settings.section("labels"))
        folder = settings.path("labels_dir")
        for sample, name in [(dev, "dev_labels.xlsx"), (blind, "blind_labels.xlsx")]:
            path = write_label_sheet(sample, folder / name)
            print(f"wrote {settings.relative(path)}: {len(sample)} titles")
        return 0
    if args.command == "make-relevance-sheet":
        from .labels import write_relevance_sheet
        from .notebook import start
        from .recommend import build_index
        from .steps.recommend import RELEVANCE_SHEET, evaluation_results, relevance_items

        project = start(verbose=False)
        rules = settings.section("recommend")
        index = build_index(project.read_parquet("recommend_jobs.parquet"), rules)
        items = relevance_items(evaluation_results(index, rules), int(rules["sheet_seed"]))
        path = write_relevance_sheet(items, rules["profiles"], settings.path("labels_dir") / RELEVANCE_SHEET)
        print(f"wrote {settings.relative(path)}: {len(items)} titles to judge for {items['profile_id'].nunique()} profiles")
        return 0
    if args.command == "serve":
        try:
            from job_market_web import create_app
        except ImportError:
            print("The web package is not installed. Run: pip install -e . --no-deps")
            return 1
        print("Loading the verified build and building the search index (about 20 seconds)...")
        app = create_app()
        print(f"Ready: open http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}  (Ctrl+C to stop)")
        app.run(host=args.host, port=args.port, debug=False)
        return 0
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
