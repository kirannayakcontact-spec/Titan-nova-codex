"""Node gateway integration helpers."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from backend.config import get_config


def _call_gateway(method: str, path: str, payload: dict | None = None) -> tuple[int, Any]:
    config = get_config()
    url = f"{config.gateway_url.rstrip('/')}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=config.gateway_timeout_seconds) as response:  # nosec - configured gateway URL
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return 503, {"status": "unavailable", "error": str(exc), "gatewayUrl": get_config().gateway_url}


def gateway_status() -> dict:
    """Return live gateway status when reachable."""

    status, payload = _call_gateway("GET", "/api/whatsapp/status")
    payload.setdefault("gatewayUrl", get_config().gateway_url)
    payload.setdefault("httpStatus", status)
    return payload


def send_whatsapp_message(to: str, message: str) -> dict:
    if not to or not message:
        raise ValueError("to and message are required")
    status, payload = _call_gateway("POST", "/api/whatsapp/messages", {"to": to, "message": message})
    payload.setdefault("httpStatus", status)
    return payload
