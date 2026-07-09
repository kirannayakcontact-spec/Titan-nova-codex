"""Setup Control Center routes.

This module exposes one safe read-only endpoint for deployment checks. It avoids
returning secrets and keeps the existing wallet, ledger, markets, payments and
WhatsApp routes untouched.
"""

from __future__ import annotations

from flask import jsonify

from backend.config import get_config
from backend.services.firebase import firebase_status, get_collection


def _collection_count(path: str) -> int:
    """Return a defensive count for a Firebase/local collection."""

    try:
        return len(get_collection(path))
    except Exception:  # pragma: no cover - status endpoint must not break dashboard
        return 0


def _recommendations(configured: dict) -> list[dict]:
    items: list[dict] = []
    if not configured["firebase"]["configured"]:
        items.append(
            {
                "level": "warning",
                "code": "firebase_env_missing",
                "message": "FIREBASE_URL/FIREBASE_DB_URL missing hai; app local fallback store use karega.",
            }
        )
    if configured["security"]["adminTokenConfigured"] is False:
        items.append(
            {
                "level": "warning",
                "code": "admin_token_missing",
                "message": "TITAN_ADMIN_TOKEN set karo taaki admin APIs protected rahein.",
            }
        )
    if configured["gateway"]["url"].startswith("http://127.0.0.1") or configured["gateway"]["url"].startswith("http://localhost"):
        items.append(
            {
                "level": "info",
                "code": "local_gateway_url",
                "message": "GATEWAY_URL local hai; same device/Termux session me gateway chalna chahiye.",
            }
        )
    if not items:
        items.append({"level": "ok", "code": "ready", "message": "Core runtime settings ready dikh rahe hain."})
    return items


def register(app):
    @app.get("/api/setup/status")
    def setup_status():
        cfg = get_config()
        fb = firebase_status()
        configured = {
            "app": {
                "name": cfg.app_name,
                "host": cfg.host,
                "port": cfg.port,
            },
            "firebase": fb,
            "gateway": {
                "url": cfg.gateway_url,
                "timeoutSeconds": cfg.gateway_timeout_seconds,
                "statusUrl": "/api/whatsapp/status",
            },
            "security": {
                "adminTokenConfigured": bool(cfg.admin_token),
            },
        }
        modules = {
            "wallets": _collection_count("wallets"),
            "ledgerEntries": _collection_count("ledger_entries"),
            "walletTransactions": _collection_count("wallet_transactions"),
            "markets": _collection_count("markets"),
            "whatsappMessages": _collection_count("whatsapp/messages"),
        }
        return jsonify(
            {
                "status": "ok",
                "module": "setup",
                "title": "Setup Control Center",
                "configured": configured,
                "modules": modules,
                "recommendations": _recommendations(configured),
            }
        )
