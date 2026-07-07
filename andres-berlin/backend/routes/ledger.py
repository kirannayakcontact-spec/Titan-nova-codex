"""Ledger routes."""

from flask import jsonify, request

from backend.services.ledger_service import create_ledger_entry, ledger_summary, list_ledger_entries


def register(app):
    @app.get("/api/ledger/summary")
    def ledger_status():
        return jsonify(ledger_summary(request.args.get("account")))

    @app.get("/api/ledger/entries")
    def ledger_entries():
        return jsonify(
            {
                "entries": list_ledger_entries(
                    account=request.args.get("account"),
                    limit=int(request.args.get("limit", 100)),
                    before_created_at=request.args.get("beforeCreatedAt"),
                    user_id=request.args.get("userId"),
                )
            }
        )

    @app.post("/api/ledger/entries")
    def ledger_create_entry():
        body = request.get_json(silent=True) or {}
        try:
            entry = create_ledger_entry(
                body.get("account", ""),
                body.get("amount"),
                body.get("type", "credit"),
                body.get("description", ""),
                body.get("reference", ""),
                body.get("userId"),
            )
            return jsonify(entry), 201
        except ValueError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
