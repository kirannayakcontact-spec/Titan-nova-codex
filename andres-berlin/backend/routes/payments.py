"""Payment routes."""

from flask import jsonify, request

from backend.services.ledger_service import create_ledger_entry
from backend.services.wallet_service import apply_wallet_transaction, list_wallet_transactions


def register(app):
    @app.get("/api/payments/status")
    def payments_status():
        return jsonify({"status": "ok", "module": "payments", "recent": list_wallet_transactions(limit=10)})

    @app.post("/api/payments")
    def create_payment():
        body = request.get_json(silent=True) or {}
        try:
            result = apply_wallet_transaction(body.get("userId", ""), body.get("amount"), "credit", body.get("description", "payment"), body.get("reference", ""))
            create_ledger_entry(f"wallet:{body.get('userId', '')}", body.get("amount"), "credit", "payment", result["transaction"]["id"])
            return jsonify(result), 201
        except ValueError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
