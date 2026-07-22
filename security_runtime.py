"""Central HTTP hardening for the Titan Flask compatibility runtime."""

from __future__ import annotations

import os
import re
from typing import Any

from flask import jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


SAFE_ID = re.compile(r"^[A-Za-z0-9_.:@+\-]{1,160}$")


def _depth(value: Any, level: int = 0) -> int:
    if level > 12:
        return level
    if isinstance(value, dict):
        return max([level, *(_depth(v, level + 1) for v in value.values())])
    if isinstance(value, list):
        return max([level, *(_depth(v, level + 1) for v in value)])
    return level


def register_security_runtime(app):
    """Apply limits, strict origin handling, payload bounds, and browser headers."""
    if getattr(app, "_titan_security_registered", False):
        return
    app._titan_security_registered = True
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("TITAN_MAX_REQUEST_BYTES", "8388608"))

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        storage_uri=os.getenv("RATELIMIT_STORAGE_URI", os.getenv("REDIS_URL", "memory://")),
        default_limits=[os.getenv("TITAN_DEFAULT_RATE_LIMIT", "240 per minute")],
        meta_limits=["20 per minute"],
    )
    critical = {
        "auth": os.getenv("TITAN_AUTH_RATE_LIMIT", "10 per minute"),
        "deposit": os.getenv("TITAN_DEPOSIT_RATE_LIMIT", "12 per minute"),
        "admin": os.getenv("TITAN_ADMIN_RATE_LIMIT", "30 per minute"),
    }
    for rule in list(app.url_map.iter_rules()):
        path = rule.rule.lower()
        category = next((name for name in critical if f"/{name}" in path), None)
        if category and rule.endpoint in app.view_functions:
            app.view_functions[rule.endpoint] = limiter.limit(critical[category])(
                app.view_functions[rule.endpoint]
            )

    allowed = {x.strip().rstrip("/") for x in os.getenv(
        "TITAN_ALLOWED_ORIGINS", "http://127.0.0.1:5000,http://localhost:5000"
    ).split(",") if x.strip()}

    @app.before_request
    def validate_request():
        origin = request.headers.get("Origin", "").rstrip("/")
        same_origin = request.host_url.rstrip("/")
        if origin and origin not in allowed and origin != same_origin:
            return jsonify({"ok": False, "error": "origin_not_allowed"}), 403
        if request.method in {"POST", "PUT", "PATCH"} and request.is_json:
            payload = request.get_json(silent=True)
            if payload is None or not isinstance(payload, (dict, list)):
                return jsonify({"ok": False, "error": "invalid_json_payload"}), 400
            if _depth(payload) > 10:
                return jsonify({"ok": False, "error": "payload_too_deep"}), 400
        for key, value in request.view_args.items() if request.view_args else ():
            if key.endswith("id") and not SAFE_ID.fullmatch(str(value)):
                return jsonify({"ok": False, "error": "invalid_identifier"}), 400

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin and (origin in allowed or origin == request.host_url.rstrip("/")):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Admin-User"
        return response

    app.extensions["titan_limiter"] = limiter
