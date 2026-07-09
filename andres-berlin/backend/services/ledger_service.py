"""Ledger business logic backed by the shared runtime store."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from backend.services.firebase import get_collection, get_record, mutate_record, push_record, set_record


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money(value: Any) -> str:
    try:
        return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("amount must be a valid number") from exc


def _index_key(created_at: str, record_id: str) -> str:
    return f"{created_at}_{record_id}"


def _limited(value: int, maximum: int) -> int:
    return max(1, min(value, maximum))


def _summary_path(account: str | None = None) -> str:
    return f"ledger_summary_totals/{account}" if account else "ledger_summary_totals/global"


def _apply_ledger_totals(account: str, amount: Decimal, entry_type: str) -> None:
    def apply(path: str) -> None:
        def update(summary: Any | None) -> dict:
            current = summary if isinstance(summary, dict) else {}
            entries = int(current.get("entries", 0)) + 1
            credits = Decimal(str(current.get("credits", "0")))
            debits = Decimal(str(current.get("debits", "0")))
            if entry_type == "credit":
                credits += amount
            else:
                debits += amount
            return {
                "entries": entries,
                "credits": f"{credits.quantize(Decimal('0.01'))}",
                "debits": f"{debits.quantize(Decimal('0.01'))}",
                "balance": f"{(credits - debits).quantize(Decimal('0.01'))}",
                "updatedAt": _now(),
            }

        mutate_record(path, update)

    apply(_summary_path())
    apply(_summary_path(account))


def create_ledger_entry(
    account: str,
    amount: Any,
    entry_type: str,
    description: str = "",
    reference: str = "",
    user_id: str | None = None,
) -> dict:
    if not account:
        raise ValueError("account is required")
    if entry_type not in {"credit", "debit"}:
        raise ValueError("entry_type must be credit or debit")
    amount_value = Decimal(_money(amount))
    entry = {
        "id": uuid4().hex,
        "account": account,
        "userId": user_id or account,
        "type": entry_type,
        "amount": f"{amount_value}",
        "description": description,
        "reference": reference,
        "createdAt": _now(),
    }
    push_record("ledger_entries", entry, entry["id"])
    set_record(
        f"ledger_entries_by_user/{entry['userId']}/{_index_key(entry['createdAt'], entry['id'])}",
        entry,
    )
    set_record(
        f"ledger_entries_by_account/{account}/{_index_key(entry['createdAt'], entry['id'])}",
        entry,
    )
    _apply_ledger_totals(account, amount_value, entry_type)
    return entry


def list_ledger_entries(
    account: str | None = None,
    limit: int = 100,
    before_created_at: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    bounded_limit = _limited(limit, 500)
    if user_id:
        entries = list(get_collection(f"ledger_entries_by_user/{user_id}").values())
        if account:
            entries = [entry for entry in entries if entry.get("account") == account]
    elif account:
        entries = list(get_collection(f"ledger_entries_by_account/{account}").values())
    else:
        entries = list(get_collection("ledger_entries").values())
    if before_created_at:
        entries = [entry for entry in entries if entry.get("createdAt", "") < before_created_at]
    entries.sort(
        key=lambda entry: _index_key(entry.get("createdAt", ""), entry.get("id", "")),
        reverse=True,
    )
    return entries[:bounded_limit]


def ledger_summary(account: str | None = None) -> dict:
    """Return precomputed ledger totals."""

    totals = get_record(_summary_path(account), {}) or {}
    return {
        "status": "ok",
        "module": "ledger",
        "entries": int(totals.get("entries", 0)),
        "credits": str(totals.get("credits", "0.00")),
        "debits": str(totals.get("debits", "0.00")),
        "balance": str(totals.get("balance", "0.00")),
    }


def record_market(symbol: str, price: Any, source: str = "manual") -> dict:
    if not symbol:
        raise ValueError("symbol is required")
    quote = {
        "symbol": symbol.upper(),
        "price": _money(price),
        "source": source,
        "updatedAt": _now(),
    }
    set_record(f"markets/{quote['symbol']}", quote)
    return quote
