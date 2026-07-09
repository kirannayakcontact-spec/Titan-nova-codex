"""Node gateway integration helpers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.config import get_config

_STATUS_CACHE: dict[str, dict[str, Any] | None] = {"success": None, "failure": None}
_STATUS_CACHE_LOCK = Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_status(kind: str, payload: dict[str, Any]) -> None:
    cached = deepcopy(payload)
    cached.setdefault("cachedAt", _utc_now())
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE[kind] = cached


def _cached_status(kind: str) -> dict[str, Any] | None:
    with _STATUS_CACHE_LOCK:
        cached = _STATUS_CACHE.get(kind)
        return deepcopy(cached) if cached is not None else None


def _call_gateway(method: str, path: str, payload: dict | None = None) -> tuple[int, Any]:
    config = get_config()
    url = f"{config.gateway_url.rstrip('/')}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=config.gateway_timeout_seconds) as response:  # nosec - configured gateway URL
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
            payload = json.loads(body) if body else {}
        except (OSError, json.JSONDecodeError):
            payload = {"error": str(exc)}
        payload.setdefault("status", "unavailable")
        payload.setdefault("error", str(exc))
        payload.setdefault("gatewayUrl", config.gateway_url)
        return exc.code, payload
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return 503, {"status": "unavailable", "error": str(exc), "gatewayUrl": config.gateway_url}


def gateway_status() -> dict:
    """Return live gateway status, falling back to stale cached data when unreachable."""

    status, payload = _call_gateway("GET", "/api/whatsapp/status")
    config = get_config()
    payload.setdefault("gatewayUrl", config.gateway_url)
    payload.setdefault("httpStatus", status)
    payload["checkedAt"] = _utc_now()

    if status < 500 and payload.get("status") != "unavailable":
        payload["stale"] = False
        _cache_status("success", payload)
        return payload

    failure_payload = deepcopy(payload)
    failure_payload["stale"] = False
    _cache_status("failure", failure_payload)

    cached_success = _cached_status("success")
    if cached_success is None:
        return failure_payload

    cached_success["stale"] = True
    cached_success["gatewayReachable"] = False
    cached_success["lastError"] = failure_payload.get("error", "Gateway unavailable")
    cached_success["lastFailedAt"] = failure_payload.get("checkedAt")
    cached_success.setdefault("gatewayUrl", config.gateway_url)
    return cached_success


def send_whatsapp_message(to: str, message: str) -> dict:
    if not to or not message:
        raise ValueError("to and message are required")
    status, payload = _call_gateway("POST", "/api/whatsapp/messages", {"to": to, "message": message})
    payload.setdefault("httpStatus", status)
    return payload
