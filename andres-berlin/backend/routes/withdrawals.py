"""Withdrawal routes."""

from flask import jsonify


def register(app):
    @app.get("/api/withdrawals/status")
    def withdrawals_status():
        return jsonify({"status": "ok", "module": "withdrawals"})
