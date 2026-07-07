"""Ledger routes."""

from flask import jsonify

from backend.services.ledger_service import ledger_summary


def register(app):
    @app.get("/api/ledger/summary")
    def ledger_status():
        return jsonify(ledger_summary())
