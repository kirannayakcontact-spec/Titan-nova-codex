"""Withdrawal routes."""

from flask import jsonify, request

from backend.services.ledger_service import create_ledger_entry
from backend.services.wallet_service import apply_wallet_transaction, list_wallet_transactions


def register(app):
    @app.get("/api/withdrawals/status")
    def withdrawals_status():
        withdrawals = [tx for tx in list_wallet_transactions(limit=100) if tx.get("type") == "debit"]
        return jsonify({"status": "ok", "module": "withdrawals", "recent": withdrawals[:10]})

    @app.post("/api/withdrawals")
    def create_withdrawal():
        body = request.get_json(silent=True) or {}
        try:
            result = apply_wallet_transaction(body.get("userId", ""), body.get("amount"), "debit", body.get("description", "withdrawal"), body.get("reference", ""))
            create_ledger_entry(f"wallet:{body.get('userId', '')}", body.get("amount"), "debit", "withdrawal", result["transaction"]["id"])
            return jsonify(result), 201
        except ValueError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
