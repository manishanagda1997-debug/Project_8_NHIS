"""Docker files (decision D-038): structural checks that need no Docker engine.

The images themselves are built and smoke-tested in CI (the `docker` job);
the end-to-end run with the mounted processed build happens locally.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
APP = (ROOT / "docker" / "app" / "Dockerfile").read_text(encoding="utf-8")
NGINX = (ROOT / "docker" / "nginx" / "Dockerfile").read_text(encoding="utf-8")
NGINX_CONF = (ROOT / "docker" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
IGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()


def service_block(name: str) -> str:
    start = COMPOSE.index(f"\n  {name}:\n")
    rest = COMPOSE[start + 1:]
    following = [rest.index(f"\n  {other}:\n") for other in ("app", "nginx", "pipeline")
                 if other != name and f"\n  {other}:\n" in rest]
    return rest[: min(following)] if following else rest


def test_each_service_has_a_pinned_dockerfile():
    assert APP.startswith("#") and "FROM mambaorg/micromamba:1.5.10" in APP
    assert "FROM nginx:1.27.3-alpine" in NGINX
    assert ":latest" not in APP + NGINX + COMPOSE


def test_app_image_uses_the_project_environment_and_a_non_root_user():
    assert "--file /app/environment.yml" in APP
    assert APP.rstrip().splitlines()[-1].strip().endswith('"job_market_web.wsgi:app"]')
    users = [line for line in APP.split("CMD")[0].splitlines() if line.startswith("USER")]
    assert users[-1] == "USER $MAMBA_USER"                                  # runs as non-root
    env = (ROOT / "environment.yml").read_text(encoding="utf-8")
    assert "prefix:" not in env and "gunicorn" not in env    # environment.yml must also install on Windows
    assert "gunicorn=23.0.0" in APP                          # pinned in the Linux image instead


def test_single_gunicorn_worker_with_threads():
    assert '"--workers", "1"' in APP and '"--threads", "4"' in APP


def test_only_nginx_is_published_and_data_is_read_only_for_the_app():
    app, nginx, pipeline = service_block("app"), service_block("nginx"), service_block("pipeline")
    assert "ports:" not in app and "expose:" in app
    assert "- ./data/processed:/app/data/processed:ro" in app
    assert '"8080:80"' in nginx and "condition: service_healthy" in nginx
    assert "/api/health" in app and "start_period:" in app
    assert 'profiles: ["pipeline"]' in pipeline
    assert "- ./data/raw:/app/data/raw:ro" in pipeline and "- ./data/labels:/app/data/labels:ro" in pipeline
    assert "- ./data/processed:/app/data/processed\n" in pipeline        # the pipeline writes outputs


def test_config_is_mounted_read_only_in_app_and_pipeline():
    # The containers read the current settings and recommender approval, not
    # the copy made when the image was built.
    for name in ("app", "pipeline"):
        assert "- ./config:/app/config:ro" in service_block(name)
    assert "./config" not in service_block("nginx")


def test_nginx_forwards_to_the_app_service():
    assert "server app:8000;" in NGINX_CONF and "proxy_pass http://jobmarket_app;" in NGINX_CONF


def test_dockerignore_keeps_data_and_secrets_out():
    for entry in ("data", ".git", ".env", "**/*.sqlite", "notebooks", "tests"):
        assert entry in IGNORE
    for needed in ("src", "config", "sql", "environment.yml", "docker"):
        assert needed not in IGNORE


def test_wsgi_module_exposes_app_without_extra_logic():
    text = (ROOT / "src" / "job_market_web" / "wsgi.py").read_text(encoding="utf-8")
    assert "app = create_app()" in text
