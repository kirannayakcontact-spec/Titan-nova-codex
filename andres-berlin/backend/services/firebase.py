"""Firebase service facade with a local JSON fallback store.

The facade targets the Firebase Realtime Database REST API when
``FIREBASE_URL``/``FIREBASE_DB_URL`` is configured and transparently falls back
onto a small JSON file for local development and tests.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.config import get_config

_LOCK = threading.RLock()
_STORE = Path(os.environ.get("TITAN_STORE_PATH", Path(__file__).resolve().parents[2] / "data" / "runtime_store.json"))
_MISSING = object()
_HIGH_GROWTH_COLLECTIONS = (
    "wallet_transactions",
    "wallet_transactions_by_user",
    "ledger_entries",
    "ledger_entries_by_user",
    "ledger_entries_by_account",
    "whatsapp/messages",
    "whatsapp/inbound",
)
_STORE_CACHE: dict[Path, tuple[int | None, dict]] = {}
_FIREBASE_DEFAULT_TIMEOUT_SECONDS = 1.5
_FIREBASE_DEFAULT_FAILURE_THRESHOLD = 2
_FIREBASE_DEFAULT_COOLDOWN_SECONDS = 15.0
_firebase_consecutive_failures = 0
_firebase_unavailable_until = 0.0


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _firebase_timeout_seconds() -> float:
    return _env_float("FIREBASE_TIMEOUT_SECONDS", _FIREBASE_DEFAULT_TIMEOUT_SECONDS, minimum=0.1)


def _firebase_failure_threshold() -> int:
    return _env_int("FIREBASE_FAILURE_THRESHOLD", _FIREBASE_DEFAULT_FAILURE_THRESHOLD, minimum=1)


def _firebase_cooldown_seconds() -> float:
    return _env_float("FIREBASE_CIRCUIT_BREAKER_SECONDS", _FIREBASE_DEFAULT_COOLDOWN_SECONDS, minimum=0.0)


def _firebase_circuit_open(now: float | None = None) -> bool:
    return (time.monotonic() if now is None else now) < _firebase_unavailable_until


def _clean_path(path: str) -> str:
    cleaned = "/".join(part for part in str(path).strip("/").split("/") if part)
    if not cleaned:
        raise ValueError("firebase path is required")
    return cleaned


def firebase_status() -> dict:
    """Return Firebase configuration and fallback status without exposing secrets."""

    url = get_config().firebase_url
    now = time.monotonic()
    unavailable_for = max(0.0, _firebase_unavailable_until - now)
    return {
        "configured": bool(url),
        "urlPreview": url[:24] + "..." if url else "",
        "fallbackStore": str(_STORE),
        "shardedCollections": list(_HIGH_GROWTH_COLLECTIONS),
        "timeoutSeconds": _firebase_timeout_seconds(),
        "failureThreshold": _firebase_failure_threshold(),
        "circuitBreakerSeconds": _firebase_cooldown_seconds(),
        "consecutiveFailures": _firebase_consecutive_failures,
        "usingLocalFallback": not bool(url) or unavailable_for > 0,
        "firebaseUnavailable": unavailable_for > 0,
        "firebaseUnavailableForSeconds": round(unavailable_for, 3),
    }


def _firebase_url(path: str, params: dict[str, str] | None = None) -> str:
    base = get_config().firebase_url.rstrip("/")
    query = f"?{urlencode(params)}" if params else ""
    return f"{base}/{_clean_path(path)}.json{query}"


def _auth_params() -> dict[str, str]:
    token = os.environ.get("FIREBASE_AUTH_TOKEN") or os.environ.get("FIREBASE_DATABASE_SECRET", "")
    return {"auth": token} if token else {}


def _firebase_request(method: str, path: str, payload: Any | None = None) -> Any:
    """Call Firebase unless the fallback circuit is open."""

    global _firebase_consecutive_failures, _firebase_unavailable_until

    if not get_config().firebase_url:
        return _MISSING

    now = time.monotonic()
    if _firebase_circuit_open(now):
        return _MISSING

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(_firebase_url(path, _auth_params()), data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=_firebase_timeout_seconds()) as response:  # nosec - configured service URL
            body = response.read().decode("utf-8")
            result = json.loads(body) if body else None
    except (OSError, URLError, json.JSONDecodeError):
        with _LOCK:
            _firebase_consecutive_failures += 1
            if _firebase_consecutive_failures >= _firebase_failure_threshold():
                _firebase_unavailable_until = time.monotonic() + _firebase_cooldown_seconds()
        return _MISSING

    with _LOCK:
        _firebase_consecutive_failures = 0
        _firebase_unavailable_until = 0.0
    return result


def _collection_store_path(collection: str) -> Path:
    safe_name = collection.replace("/", "__")
    return _STORE.with_suffix("") / f"{safe_name}.json"


def _local_store_for(path: str) -> tuple[Path, str | None]:
    cleaned = _clean_path(path)
    for collection in _HIGH_GROWTH_COLLECTIONS:
        if cleaned == collection:
            return _collection_store_path(collection), None
        prefix = f"{collection}/"
        if cleaned.startswith(prefix):
            return _collection_store_path(collection), cleaned[len(prefix) :]
    return _STORE, cleaned


def _file_mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def _read_store_file(path: Path) -> dict:
    mtime = _file_mtime_ns(path)
    cached = _STORE_CACHE.get(path)
    if cached and cached[0] == mtime:
        return json.loads(json.dumps(cached[1]))
    if mtime is None:
        data: dict = {}
    else:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            data = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            data = {}
    _STORE_CACHE[path] = (mtime, data)
    return json.loads(json.dumps(data))


def _write_store_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    _STORE_CACHE[path] = (_file_mtime_ns(path), json.loads(json.dumps(data)))


def _read_local(path: str) -> Any | None:
    store_path, inner_path = _local_store_for(path)
    data = _read_store_file(store_path)
    if inner_path is None:
        return data
    cursor: Any = data
    for part in inner_path.split("/"):
        if not isinstance(cursor, dict) or part not in cursor:
            return _MISSING
        cursor = cursor[part]
    return cursor


def _write_local(path: str, mutator: Callable[[dict, str | None], Any]) -> Any:
    store_path, inner_path = _local_store_for(path)
    data = _read_store_file(store_path)
    result = mutator(data, inner_path)
    _write_store_file(store_path, data)
    return result


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
        value = _read_local(path)
        return default if value is _MISSING else value


def set_record(path: str, value: Any) -> Any:
    """Replace a value at a Firebase path."""

    remote = _firebase_request("PUT", path, value)
    if remote is not _MISSING:
        return remote
    with _LOCK:
        def mutator(data: dict, inner_path: str | None) -> Any:
            if inner_path is None:
                data.clear()
                if isinstance(value, dict):
                    data.update(value)
                else:
                    data["value"] = value
            else:
                cursor, leaf = _walk(data, inner_path, create=True)
                cursor[leaf] = value
            return value

        return _write_local(path, mutator)


def update_record(path: str, updates: dict) -> dict:
    """Merge dictionary fields into an existing Firebase object."""

    if not isinstance(updates, dict):
        raise ValueError("updates must be a dictionary")
    remote = _firebase_request("PATCH", path, updates)
    if remote is not _MISSING:
        return remote if isinstance(remote, dict) else updates
    with _LOCK:
        def mutator(data: dict, inner_path: str | None) -> dict:
            if inner_path is None:
                data.update(updates)
                return data
            cursor, leaf = _walk(data, inner_path, create=True)
            current = cursor.get(leaf, {})
            if not isinstance(current, dict):
                current = {}
            current.update(updates)
            cursor[leaf] = current
            return current

        return _write_local(path, mutator)


def delete_record(path: str) -> bool:
    """Delete a Firebase value."""

    remote = _firebase_request("DELETE", path)
    if remote is not _MISSING:
        return True
    with _LOCK:
        def mutator(data: dict, inner_path: str | None) -> bool:
            if inner_path is None:
                data.clear()
                return True
            cursor, leaf = _walk(data, inner_path)
            if leaf in cursor:
                del cursor[leaf]
            return True

        return _write_local(path, mutator)


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
