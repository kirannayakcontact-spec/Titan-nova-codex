"""Lightweight dashboard summary routes."""

from decimal import Decimal

from flask import jsonify

from backend.services.firebase import get_collection


def _money_total(items: list[dict], entry_type: str) -> str:
    total = sum((Decimal(str(item.get("amount", "0"))) for item in items if item.get("type") == entry_type), Decimal("0"))
    return f"{total.quantize(Decimal('0.01'))}"


def register(app):
    @app.get("/api/dashboard/summary")
    def dashboard_summary():
        wallets = get_collection("wallets")
        ledger_entries = list(get_collection("ledger_entries").values())
        transactions = list(get_collection("wallet_transactions").values())
        markets = get_collection("markets")
        withdrawal_count = sum(1 for tx in transactions if tx.get("type") == "debit")

        return jsonify(
            {
                "status": "ok",
                "modules": {
                    "wallet": {"status": "ok", "wallets": len(wallets)},
                    "ledger": {
                        "status": "ok",
                        "entries": len(ledger_entries),
                        "credits": _money_total(ledger_entries, "credit"),
                        "debits": _money_total(ledger_entries, "debit"),
                    },
                    "markets": {"status": "ok", "markets": len(markets)},
                    "payments": {"status": "ok", "transactions": len(transactions)},
                    "withdrawals": {"status": "ok", "withdrawals": withdrawal_count},
                    "admin": {"status": "ok"},
                    "whatsapp": {"status": "not_checked"},
                },
            }
        )
