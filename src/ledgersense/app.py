"""Flask application factory: serves the built React frontend and the API."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, send_from_directory

from .api import api_blueprint

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(_STATIC_DIR), static_url_path="")
    app.register_blueprint(api_blueprint)

    @app.get("/")
    def index() -> Response:
        index_path = _STATIC_DIR / "index.html"
        if not index_path.exists():
            return Response(
                "Frontend build not found. Run `npm ci && npm run build` in frontend/ first.",
                status=501,
                mimetype="text/plain",
            )
        return send_from_directory(_STATIC_DIR, "index.html")

    return app


# `flask --app ledgersense.app:create_app run` calls create_app() directly, so
# no module-level app instance is needed here.
