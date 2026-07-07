"""Lightweight Titan Nova runtime smoke test.

This test intentionally avoids calling Firebase-backed routes. It imports the Flask
app and verifies that the core dashboard/API routes are registered, so a broken
route registration or missing two-file runtime dependency is caught before deploy.
"""

import importlib.machinery
import importlib.util
import os
from pathlib import Path

os.environ.setdefault("TITAN_SECURITY_DISABLED", "1")
os.environ.setdefault("APP_TZ", "Asia/Kolkata")
os.environ.setdefault("TITAN_BUSINESS_DAY_CUTOFF_HOUR", "6")
os.environ.setdefault("FIREBASE_URL", "https://example.invalid/titan_master_data.json")

ROOT = Path(__file__).resolve().parent


def _load_flask_app():
    try:
        import flask_app  # type: ignore  # noqa: E402

        return flask_app
    except ModuleNotFoundError as exc:
        if exc.name != "flask_app":
            raise

    backup = ROOT / "legacy-backup" / "flask_app.py.bak"
    loader = importlib.machinery.SourceFileLoader("flask_app", str(backup))
    spec = importlib.util.spec_from_loader("flask_app", loader)
    if spec is None:
        raise RuntimeError(f"Unable to load {backup}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


flask_app = _load_flask_app()


def main() -> None:
    app = getattr(flask_app, "app", None)
    if app is None:
        raise SystemExit("flask_app.app missing")

    routes = {rule.rule for rule in app.url_map.iter_rules()}
    required = {
        "/",
        "/api/security_status",
        "/api/admin_login",
        "/api/admin_logout",
        "/api/firebase_data_guard_status",
        "/api/deposit_flow_v1/status",
        "/api/deposit_flow_v1/settings",
        "/api/deposit_flow_v1/setup_ui",
    }
    missing = sorted(required - routes)
    if missing:
        raise SystemExit("Missing required routes: " + ", ".join(missing))

    print("Titan Nova smoke test OK: core Flask routes registered")


if __name__ == "__main__":
    main()
