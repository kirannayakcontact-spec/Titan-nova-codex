"""Payment routes."""

from flask import jsonify


def register(app):
    @app.get("/api/payments/status")
    def payments_status():
        return jsonify({"status": "ok", "module": "payments"})
