"""Wallet routes."""

from flask import jsonify

from backend.services.wallet_service import wallet_summary


def register(app):
    @app.get("/api/wallet/summary")
    def wallet_status():
        return jsonify(wallet_summary())
