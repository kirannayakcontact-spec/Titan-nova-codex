"""Market routes."""

from flask import jsonify, request

from backend.services.firebase import get_collection
from backend.services.ledger_service import record_market


def register(app):
    @app.get("/api/markets/status")
    def markets_status():
        markets = get_collection("markets")
        return jsonify({"status": "ok", "module": "markets", "markets": len(markets), "quotes": list(markets.values())})

    @app.get("/api/markets/<symbol>")
    def market_detail(symbol):
        quote = get_collection("markets").get(symbol.upper())
        return (jsonify(quote), 200) if quote else (jsonify({"status": "error", "error": "market not found"}), 404)

    @app.post("/api/markets")
    def market_create():
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(record_market(body.get("symbol", ""), body.get("price"), body.get("source", "manual"))), 201
        except ValueError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
