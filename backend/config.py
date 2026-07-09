"""Titan Nova backend configuration helpers.

Phase 1 module scaffold.

This module is safe to import and does not create a Flask app or connect to
Firebase at import time. `flask_app.py` remains the active runtime entry until a
later compatibility phase imports these helpers.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from typing import Dict, List


DEFAULT_FIREBASE_URL = "https://titan-bbbc4-default-rtdb.firebaseio.com/titan_master_data.json"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:3000"
DEFAULT_APP_TZ = "Asia/Kolkata"


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def env_str(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def env_bool(name: str, default: bool = False) -> bool:
    raw = env_str(name, "1" if default else "0").lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return bool(default)


def env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(env_str(name, str(default)) or default)
    except Exception:
        value = int(default)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def normalize_firebase_url(url: str) -> str:
    url = str(url or "").strip().rstrip("/")
    if url and not url.endswith(".json"):
        url = url + ".json"
    return url or DEFAULT_FIREBASE_URL


def is_localhost_url(url: str) -> bool:
    return bool(re.search(r"https?://(127\.0\.0\.1|localhost)(:|/|$)", str(url or ""), re.I))


def redact(value: str, keep: int = 18) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= keep:
        return text
    left = max(6, keep // 2)
    right = max(4, keep - left)
    return text[:left] + "…" + text[-right:]


@dataclass(frozen=True)
class BackendConfig:
    firebase_url: str
    firebase_from_env: bool
    gateway_url: str
    gateway_is_localhost: bool
    app_tz: str
    business_day_cutoff_hour: int
    admin_token_configured: bool
    gateway_token_configured: bool
    security_disabled: bool
    production_mode: bool
    allow_query_token: bool
    realtime_fast_sync: bool
    state_cache_ttl_ms: int

    def public_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["firebase_url"] = redact(self.firebase_url, 24)
        data["gateway_url"] = redact(self.gateway_url, 24)
        return data


def load_backend_config() -> BackendConfig:
    firebase_raw = env_str("FIREBASE_URL") or env_str("FIREBASE_DB_URL") or DEFAULT_FIREBASE_URL
    gateway_url = env_str("GATEWAY_URL", DEFAULT_GATEWAY_URL).rstrip("/") or DEFAULT_GATEWAY_URL
    env_name = env_str("TITAN_ENV") or env_str("FLASK_ENV")
    production_mode = env_name.lower() in {"prod", "production"}
    return BackendConfig(
        firebase_url=normalize_firebase_url(firebase_raw),
        firebase_from_env=bool(env_str("FIREBASE_URL") or env_str("FIREBASE_DB_URL")),
        gateway_url=gateway_url,
        gateway_is_localhost=is_localhost_url(gateway_url),
        app_tz=env_str("APP_TZ", DEFAULT_APP_TZ) or DEFAULT_APP_TZ,
        business_day_cutoff_hour=env_int("TITAN_BUSINESS_DAY_CUTOFF_HOUR", 6, 0, 23),
        admin_token_configured=bool(env_str("TITAN_ADMIN_TOKEN")),
        gateway_token_configured=bool(env_str("TITAN_GATEWAY_TOKEN")),
        security_disabled=env_bool("TITAN_SECURITY_DISABLED", False),
        production_mode=production_mode,
        allow_query_token=env_bool("TITAN_ALLOW_QUERY_TOKEN", False),
        realtime_fast_sync=not env_str("TITAN_REALTIME_FAST_SYNC", "1").lower() in _FALSE_VALUES,
        state_cache_ttl_ms=env_int("TITAN_STATE_CACHE_TTL_MS", 250, 0, 60000),
    )


def startup_warnings(config: BackendConfig | None = None) -> List[str]:
    cfg = config or load_backend_config()
    warnings: List[str] = []
    if not cfg.firebase_from_env:
        warnings.append("FIREBASE_URL/FIREBASE_DB_URL missing; compatibility default is in use.")
    if not cfg.admin_token_configured:
        warnings.append("TITAN_ADMIN_TOKEN missing; admin security may be compatibility-open.")
    if not cfg.gateway_token_configured:
        warnings.append("TITAN_GATEWAY_TOKEN missing; Gateway calls may rely on fallback token behavior.")
    if cfg.gateway_is_localhost:
        warnings.append("GATEWAY_URL uses localhost; OK for same-phone Termux, wrong for split-phone deploy.")
    if cfg.production_mode and cfg.security_disabled:
        warnings.append("Production mode with TITAN_SECURITY_DISABLED enabled is unsafe.")
    return warnings


__all__ = [
    "BackendConfig",
    "DEFAULT_APP_TZ",
    "DEFAULT_FIREBASE_URL",
    "DEFAULT_GATEWAY_URL",
    "env_bool",
    "env_int",
    "env_str",
    "is_localhost_url",
    "load_backend_config",
    "normalize_firebase_url",
    "redact",
    "startup_warnings",
]
