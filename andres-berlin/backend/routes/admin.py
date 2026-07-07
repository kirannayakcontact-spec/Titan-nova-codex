"""Admin routes."""

from flask import jsonify


def register(app):
    @app.get("/api/admin/status")
    def admin_status():
        return jsonify({"status": "ok", "module": "admin"})
