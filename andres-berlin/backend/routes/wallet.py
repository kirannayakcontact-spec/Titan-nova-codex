"""Wallet routes."""

from flask import jsonify, request

from backend.services.wallet_service import apply_wallet_transaction, get_wallet, list_wallet_transactions, wallet_summary


def _error(exc: Exception, status: int = 400):
    return jsonify({"status": "error", "error": str(exc)}), status


def register(app):
    @app.get("/api/wallet/summary")
    def wallet_status():
        return jsonify(wallet_summary(request.args.get("userId")))

    @app.get("/api/wallet/<user_id>")
    def wallet_detail(user_id):
        return jsonify(get_wallet(user_id))

    @app.post("/api/wallet/<user_id>/transactions")
    def wallet_transaction(user_id):
        body = request.get_json(silent=True) or {}
        try:
            result = apply_wallet_transaction(user_id, body.get("amount"), body.get("type", "credit"), body.get("description", ""), body.get("reference", ""))
            return jsonify(result), 201
        except ValueError as exc:
            return _error(exc)

    @app.get("/api/wallet/transactions")
    def wallet_transactions():
        return jsonify({"transactions": list_wallet_transactions(request.args.get("userId"), int(request.args.get("limit", 50)))})
