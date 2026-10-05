"""Flask application: recommendation page, market dashboard and JSON API (decisions D-035, D-036).

    /                       recommendation page
    /dashboard              market dashboard (Task 6)
    /api/health             is the app ready, which build and recommender
    /api/recommend          the 10 best-matching jobs for typed skills
    /api/similar/<row_id>   the 5 jobs most like one job
"""

from __future__ import annotations

from importlib import resources
from typing import Callable

from flask import Flask, Response, jsonify, render_template, request

from .service import ApiError, RecommenderService


def plotly_js() -> bytes | None:
    """plotly.js as shipped inside the installed plotly package (no internet needed)."""
    try:
        return resources.files("plotly").joinpath("package_data", "plotly.min.js").read_bytes()
    except (ModuleNotFoundError, FileNotFoundError, OSError):
        return None


def create_app(service: RecommenderService | None = None, dashboard=None,
               loader: Callable[[], tuple] | None = None) -> Flask:
    """Create the app around ready parts (tests) or parts loaded from the current, verified build."""
    if service is None:
        from .build import load_app_parts

        service, dashboard = (loader or load_app_parts)()
    app = Flask(__name__)
    app.json.sort_keys = False
    app.extensions["recommender"] = service
    app.extensions["dashboard"] = dashboard
    script = plotly_js()

    @app.errorhandler(ApiError)
    def api_error(error: ApiError):
        return jsonify({"error": error.message}), error.status

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found."}), 404
        return "Page not found.", 404

    @app.get("/")
    def index_page():
        return render_template("index.html", meta=service.meta())

    @app.get("/dashboard")
    def dashboard_page():
        if dashboard is None:
            return "The dashboard data is not loaded in this app.", 503
        from .dashboard import context

        return render_template("dashboard.html", meta=service.meta(), page=context(dashboard))

    @app.get("/static/plotly.min.js")
    def plotly_script():
        if script is None:
            return Response("// plotly is not installed", status=404, mimetype="application/javascript")
        response = Response(script, mimetype="application/javascript")
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    @app.get("/api/health")
    def health():
        return jsonify(service.health())

    @app.get("/api/recommend")
    def recommend():
        return jsonify(service.recommend(request.args.to_dict()))

    @app.get("/api/similar/<row_id>")
    def similar(row_id: str):
        if not row_id.isdigit():
            raise ApiError(400, "row_id must be a whole number.")
        return jsonify(service.similar(int(row_id), request.args.to_dict()))

    return app
