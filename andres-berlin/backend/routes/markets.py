"""Market routes."""

from flask import jsonify


def register(app):
    @app.get("/api/markets/status")
    def markets_status():
        return jsonify({"status": "ok", "module": "markets"})
