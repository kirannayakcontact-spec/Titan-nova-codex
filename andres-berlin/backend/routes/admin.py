"""Admin routes."""

from flask import jsonify, request

from backend.security import admin_token_error_response, validate_admin_token


ADMIN_API_PREFIX = "/api/admin/"


def register(app):
    @app.before_request
    def require_admin_token_for_admin_api():
        if request.path == "/api/admin" or request.path.startswith(ADMIN_API_PREFIX):
            is_valid, reason = validate_admin_token()
            if not is_valid:
                return admin_token_error_response(reason)

        return None

    @app.get("/api/admin/status")
    def admin_status():
        return jsonify({"status": "ok", "module": "admin"})
