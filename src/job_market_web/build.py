"""Load the recommender from the current, verified build.

The app checks that the code and settings match the recorded build and that
every file it reads has the recorded SHA-256. It does not need the raw CSV,
so the same check works inside a Docker image that ships only the processed
outputs.
"""

from __future__ import annotations

import pandas as pd

from job_market.config import Settings, load_settings
from job_market.environment import current_problems, enforce
from job_market.fingerprint import project_code_sha256
from job_market.manifest import IntegrityError, load_manifest, verify_output
from job_market.provenance import ServingError, serving_decision

from .service import RecommenderService

USED_OUTPUTS = ("recommend_jobs.parquet", "pay_keywords_hourly.csv", "trend_keywords.csv")


class AppBuildError(IntegrityError):
    """The processed outputs cannot serve the app (missing, stale or not evaluated)."""


def verified_path(settings: Settings, manifest: dict, name: str):
    relative = settings.relative(settings.path("processed_dir") / name)
    for entry in manifest["outputs"]:
        if entry["path"] == relative:
            return verify_output(entry, settings.root)
    raise AppBuildError(f"{name} is not an output of build {manifest['run_id']}. Run: python -m job_market rebuild")


def checked_manifest(settings: Settings) -> dict:
    """The recorded build, after checking that code and settings still match it."""
    manifest = load_manifest(settings.path("manifest"))
    recorded = manifest.get("fingerprints", {})
    stale = [label for key, label, current in (
        ("code_sha256", "code", project_code_sha256(settings)),
        ("config_sha256", "settings", settings.config_sha256),
    ) if recorded.get(key) != current]
    if stale:
        raise AppBuildError(f"The build is stale ({', '.join(stale)} changed). Run: python -m job_market rebuild")
    return manifest


def load_service(settings: Settings | None = None, manifest: dict | None = None) -> RecommenderService:
    settings = settings or load_settings()
    manifest = manifest or checked_manifest(settings)
    # The same environment rule as the pipeline and the notebooks: a printed
    # warning by default, an error in strict mode.
    enforce(current_problems(settings.root), "The app environment")
    try:
        decision = serving_decision(settings, manifest)
    except ServingError as error:
        raise AppBuildError(f"The app cannot serve this build: {error}") from error
    method = decision["method"]
    paths = {name: verified_path(settings, manifest, name) for name in USED_OUTPUTS}
    jobs = pd.read_parquet(paths["recommend_jobs.parquet"])
    pay = pd.read_csv(paths["pay_keywords_hourly.csv"])
    trend = pd.read_csv(paths["trend_keywords.csv"])
    service = RecommenderService.from_tables(jobs, settings.section("recommend"), method, manifest["run_id"], pay, trend,
                                             method_status=decision["method_status"],
                                             approval_note=decision["approval_note"],
                                             approval_ref=decision["approval_ref"],
                                             build_approval_ref=decision["build_approval_ref"])
    service.market_shares(int(settings.section("recommend")["pool_days"]))      # warm the default pool
    return service


def load_app_parts(settings: Settings | None = None):
    """The recommender service and the dashboard data, both from the same verified build."""
    from .dashboard import load_dashboard

    settings = settings or load_settings()
    manifest = checked_manifest(settings)
    return load_service(settings, manifest), load_dashboard(settings, manifest)
