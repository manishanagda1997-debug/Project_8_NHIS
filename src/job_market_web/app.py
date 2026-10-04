"""Flask application: the recommendation page and the JSON API (decision D-035).

    /                       recommendation page
    /api/health             is the app ready, which build and recommender
    /api/recommend          the 10 best-matching jobs for typed skills
    /api/similar/<row_id>   the 5 jobs most like one job
"""

from __future__ import annotations

from typing import Callable

from flask import Flask, jsonify, render_template, request

from .service import ApiError, RecommenderService


def create_app(service: RecommenderService | None = None,
               loader: Callable[[], RecommenderService] | None = None) -> Flask:
    """Create the app around a ready service (tests) or one loaded from the current build."""
    if service is None:
        from .build import load_service

        service = (loader or load_service)()
    app = Flask(__name__)
    app.json.sort_keys = False
    app.extensions["recommender"] = service

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
