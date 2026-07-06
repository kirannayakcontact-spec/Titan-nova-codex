"""Titan Nova backend health helpers.

Phase 1 module scaffold. This module is import-safe and performs no network
calls unless explicitly requested by the caller.
"""

from __future__ import annotations

import datetime as _dt
import time
from typing import Any, Dict

try:
    import requests
except Exception:  # pragma: no cover - optional during static checks
    requests = None  # type: ignore

from .config import BackendConfig, load_backend_config, startup_warnings


PHASE1_HEALTH_VERSION = "2026-07-06-phase1-health-module"


def utc_now_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def build_backend_health(config: BackendConfig | None = None) -> Dict[str, Any]:
    cfg = config or load_backend_config()
    warnings = startup_warnings(cfg)
    return {
        "status": "ok" if not warnings else "warning",
        "version": PHASE1_HEALTH_VERSION,
        "checkedAt": utc_now_iso(),
        "config": cfg.public_dict(),
        "warnings": warnings,
        "runtime": {
            "entrypoint": "flask_app.py",
            "modularPhase": "phase1-config-health-scaffold",
            "behaviorChanged": False,
        },
    }


def check_gateway_reachable(config: BackendConfig | None = None, timeout: float = 3.0) -> Dict[str, Any]:
    cfg = config or load_backend_config()
    started = time.time()
    if requests is None:
        return {
            "ok": False,
            "status": "requests_missing",
            "message": "Python requests package is unavailable.",
            "gatewayUrl": cfg.public_dict().get("gateway_url"),
            "ms": 0,
        }
    try:
        url = cfg.gateway_url.rstrip("/") + "/health"
        res = requests.get(url, timeout=timeout)
        ms = int((time.time() - started) * 1000)
        payload: Any
        try:
            payload = res.json()
        except Exception:
            payload = {"raw": getattr(res, "text", "")[:240]}
        return {
            "ok": 200 <= int(res.status_code) < 300,
            "status": "online" if 200 <= int(res.status_code) < 300 else "http_error",
            "httpStatus": int(res.status_code),
            "message": "Gateway reachable" if 200 <= int(res.status_code) < 300 else "Gateway returned HTTP error",
            "gatewayUrl": cfg.public_dict().get("gateway_url"),
            "ms": ms,
            "payload": payload,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "offline",
            "message": str(exc)[:240],
            "gatewayUrl": cfg.public_dict().get("gateway_url"),
            "localhostHint": cfg.gateway_is_localhost,
            "ms": int((time.time() - started) * 1000),
        }


__all__ = [
    "PHASE1_HEALTH_VERSION",
    "build_backend_health",
    "check_gateway_reachable",
    "utc_now_iso",
]
