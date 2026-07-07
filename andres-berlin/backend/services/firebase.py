"""Firebase service facade with a local JSON fallback store."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from backend.config import get_config

_LOCK = threading.Lock()
_STORE = Path(os.environ.get("TITAN_STORE_PATH", Path(__file__).resolve().parents[2] / "data" / "runtime_store.json"))


def firebase_status() -> dict:
    """Return Firebase configuration status without exposing secrets."""

    url = get_config().firebase_url
    return {"configured": bool(url), "urlPreview": url[:24] + "..." if url else "", "fallbackStore": str(_STORE)}


def _firebase_url(path: str) -> str:
    base = get_config().firebase_url.rstrip("/")
    return f"{base}/{path.strip('/')}.json"


def _firebase_request(method: str, path: str, payload: Any | None = None) -> Any | None:
    if not get_config().firebase_url:
        return None
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(_firebase_url(path), data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=4) as response:  # nosec - configured service URL
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except (OSError, URLError, json.JSONDecodeError):
        return None


def _read_store() -> dict:
    if not _STORE.exists():
        return {}
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_store(data: dict) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def get_record(path: str) -> Any | None:
    remote = _firebase_request("GET", path)
    if remote is not None:
        return remote
    with _LOCK:
        cursor: Any = _read_store()
        for part in path.strip("/").split("/"):
            if not isinstance(cursor, dict):
                return None
            cursor = cursor.get(part)
        return cursor


def set_record(path: str, value: Any) -> Any:
    remote = _firebase_request("PUT", path, value)
    if remote is not None:
        return remote
    with _LOCK:
        data = _read_store()
        cursor = data
        parts = path.strip("/").split("/")
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
        _write_store(data)
        return value


def get_collection(path: str) -> dict:
    value = get_record(path)
    return value if isinstance(value, dict) else {}


def append_record(collection: str, record_id: str, value: dict) -> dict:
    set_record(f"{collection}/{record_id}", value)
    return value
