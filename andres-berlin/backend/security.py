"""Security helpers for Andres Berlin."""

import hmac

from flask import jsonify, request

from backend.config import BackendConfig, get_config


def constant_time_equal(left: str, right: str) -> bool:
    """Compare strings without leaking timing information."""

    return hmac.compare_digest(str(left or ""), str(right or ""))


def get_admin_token_from_request() -> str:
    """Return an admin token supplied via header, if present."""

    authorization = request.headers.get("Authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return request.headers.get("X-Admin-Token", "").strip()


def validate_admin_token(config: BackendConfig | None = None) -> tuple[bool, str]:
    """Validate the current request's admin token against runtime config.

    Returns ``(True, "")`` when admin auth is disabled or the request has a
    valid token. Otherwise returns ``(False, reason)`` where reason is
    ``"missing"`` or ``"invalid"``.
    """

    resolved_config = config or get_config()
    expected_token = (resolved_config.admin_token or "").strip()
    if not expected_token:
        return True, ""

    supplied_token = get_admin_token_from_request()
    if not supplied_token:
        return False, "missing"

    if not constant_time_equal(supplied_token, expected_token):
        return False, "invalid"

    return True, ""


def admin_token_error_response(reason: str):
    """Return a JSON response for an admin-token validation failure."""

    if reason == "missing":
        return jsonify({"error": "admin_token_required"}), 401

    return jsonify({"error": "admin_token_invalid"}), 403
