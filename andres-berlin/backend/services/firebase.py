"""Firebase service facade with a local JSON fallback store.

The facade targets the Firebase Realtime Database REST API when
``FIREBASE_URL``/``FIREBASE_DB_URL`` is configured and transparently falls back
onto a small JSON file for local development and tests.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.config import get_config

_LOCK = threading.RLock()
_STORE = Path(os.environ.get("TITAN_STORE_PATH", Path(__file__).resolve().parents[2] / "data" / "runtime_store.json"))
_MISSING = object()


def _clean_path(path: str) -> str:
    cleaned = "/".join(part for part in str(path).strip("/").split("/") if part)
    if not cleaned:
        raise ValueError("firebase path is required")
    return cleaned


def firebase_status() -> dict:
    """Return Firebase configuration status without exposing secrets."""

    url = get_config().firebase_url
    return {"configured": bool(url), "urlPreview": url[:24] + "..." if url else "", "fallbackStore": str(_STORE)}


def _firebase_url(path: str, params: dict[str, str] | None = None) -> str:
    base = get_config().firebase_url.rstrip("/")
    query = f"?{urlencode(params)}" if params else ""
    return f"{base}/{_clean_path(path)}.json{query}"


def _auth_params() -> dict[str, str]:
    token = os.environ.get("FIREBASE_AUTH_TOKEN") or os.environ.get("FIREBASE_DATABASE_SECRET", "")
    return {"auth": token} if token else {}


def _firebase_request(method: str, path: str, payload: Any | None = None) -> Any:
    if not get_config().firebase_url:
        return _MISSING
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(_firebase_url(path, _auth_params()), data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=6) as response:  # nosec - configured service URL
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except (OSError, URLError, json.JSONDecodeError):
        return _MISSING


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


def _walk(data: dict, path: str, create: bool = False) -> tuple[dict, str]:
    cursor = data
    parts = _clean_path(path).split("/")
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            if not create:
                return {}, parts[-1]
            next_value = {}
            cursor[part] = next_value
        cursor = next_value
    return cursor, parts[-1]


def get_record(path: str, default: Any | None = None) -> Any | None:
    """Read a value from Firebase or the fallback store."""

    remote = _firebase_request("GET", path)
    if remote is not _MISSING:
        return default if remote is None else remote
    with _LOCK:
        cursor: Any = _read_store()
        for part in _clean_path(path).split("/"):
            if not isinstance(cursor, dict) or part not in cursor:
                return default
            cursor = cursor[part]
        return cursor


def set_record(path: str, value: Any) -> Any:
    """Replace a value at a Firebase path."""

    remote = _firebase_request("PUT", path, value)
    if remote is not _MISSING:
        return remote
    with _LOCK:
        data = _read_store()
        cursor, leaf = _walk(data, path, create=True)
        cursor[leaf] = value
        _write_store(data)
        return value


def update_record(path: str, updates: dict) -> dict:
    """Merge dictionary fields into an existing Firebase object."""

    if not isinstance(updates, dict):
        raise ValueError("updates must be a dictionary")
    remote = _firebase_request("PATCH", path, updates)
    if remote is not _MISSING:
        return remote if isinstance(remote, dict) else updates
    with _LOCK:
        data = _read_store()
        cursor, leaf = _walk(data, path, create=True)
        current = cursor.get(leaf, {})
        if not isinstance(current, dict):
            current = {}
        current.update(updates)
        cursor[leaf] = current
        _write_store(data)
        return current


def delete_record(path: str) -> bool:
    """Delete a Firebase value."""

    remote = _firebase_request("DELETE", path)
    if remote is not _MISSING:
        return True
    with _LOCK:
        data = _read_store()
        cursor, leaf = _walk(data, path)
        if leaf in cursor:
            del cursor[leaf]
            _write_store(data)
        return True


def get_collection(path: str) -> dict:
    value = get_record(path, {})
    return value if isinstance(value, dict) else {}


def append_record(collection: str, record_id: str, value: dict) -> dict:
    set_record(f"{collection}/{record_id}", value)
    return value


def push_record(collection: str, value: dict, record_id: str | None = None) -> dict:
    """Create a child record, returning the stored value with its id."""

    from uuid import uuid4

    item = dict(value)
    item.setdefault("id", record_id or uuid4().hex)
    return append_record(collection, item["id"], item)


def mutate_record(path: str, mutator: Callable[[Any | None], Any]) -> Any:
    """Read, mutate, and write a value under one process-local lock."""

    with _LOCK:
        current = get_record(path)
        updated = mutator(current)
        set_record(path, updated)
        return updated
