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

    routes = {}
    for rule in app.url_map.iter_rules():
        routes.setdefault(rule.rule, set()).update(rule.methods)
    required = {
        "/": {"GET"},
        "/api/plain_health": {"GET"},
        "/api/runtime_boot/status": {"GET"},
        "/api/security_status": {"GET"},
        "/api/admin_login": {"POST"},
        "/api/admin_logout": {"POST"},
        "/api/firebase_data_guard_status": {"GET"},
        "/api/state": {"GET"},
        "/api/market_registry": {"GET", "POST"},
        "/api/payments": {"GET"},
        "/api/withdrawals": {"GET"},
        "/api/wallets": {"GET"},
        "/api/entries": {"GET"},
        "/api/results": {"GET"},
        "/api/settlements": {"GET"},
        "/api/gateway_status": {"GET"},
        "/api/wa_login_status": {"GET"},
        "/api/deposit_flow_v1/status": {"GET"},
        "/api/deposit_flow_v1/settings": {"GET", "POST"},
        "/api/deposit_flow_v1/request": {"POST"},
        "/api/deposit_flow_v1/list": {"GET"},
        "/api/deposit_flow_v1/update": {"POST"},
        "/api/deposit_flow_v1/setup_ui": {"GET"},
    }
    missing = sorted(path for path in required if path not in routes)
    if missing:
        raise SystemExit("Missing required routes: " + ", ".join(missing))

    wrong_methods = []
    for path, expected_methods in required.items():
        if path not in routes:
            continue
        missing_methods = expected_methods - routes[path]
        if missing_methods:
            wrong_methods.append(f"{path} missing {','.join(sorted(missing_methods))}")
    if wrong_methods:
        raise SystemExit("Invalid route methods: " + "; ".join(wrong_methods))

    client = app.test_client()
    health = client.get("/api/plain_health")
    if health.status_code != 200 or health.get_json(silent=True, force=True).get("status") != "success":
        raise SystemExit("Plain health endpoint contract failed")

    boot = client.get("/api/runtime_boot/status")
    boot_data = boot.get_json(silent=True, force=True) or {}
    if boot.status_code != 200 or not boot_data.get("legacyLoaded"):
        raise SystemExit("Runtime boot endpoint reports an unhealthy legacy runtime")
    failed_patches = [patch for patch in boot_data.get("patches", []) if patch.get("status") == "error"]
    if failed_patches:
        raise SystemExit("Runtime patches failed: " + ", ".join(patch.get("label", "unknown") for patch in failed_patches))

    dashboard = client.get("/")
    body = dashboard.get_data(as_text=True)
    if dashboard.status_code != 200 or "<!doctype html" not in body.lower():
        raise SystemExit("Dashboard HTML contract failed")

    print(f"Titan Nova smoke test OK: {len(required)} API/UI contracts and runtime patches verified")


if __name__ == "__main__":
    main()
