# ==========================================================
# TITAN NOVA LEGACY RUNTIME LAUNCHER
# Run UI/API: python flask_app.py
# ==========================================================

from pathlib import Path
import os
import traceback
import time

os.environ.setdefault("FIREBASE_URL", "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json")
os.environ.setdefault("FIREBASE_DB_URL", os.environ.get("FIREBASE_URL"))

_LAUNCHER_NAME = __name__
_LAUNCHER_VERSION = "2026-07-10-runtime-cleanup-v8"
_BASE_DIR = Path(__file__).resolve().parent
_LEGACY_FILE = _BASE_DIR / "legacy-backup" / "flask_app.py.bak"
_BOOT_STARTED_AT = time.strftime("%Y-%m-%dT%H:%M:%S%z")
_PATCH_REPORT = []
_LEGACY_BOOT_ERROR = None
_LEGACY_BOOT_TRACEBACK = ""
_LEGACY_LOADED = False
_IS_TERMUX = bool(os.environ.get("PREFIX", "").startswith("/data/data/com.termux/"))
_SAFE_UI_BOOT = str(os.environ.get("TITAN_SAFE_UI_BOOT", "1" if _IS_TERMUX else "0")).strip().lower() not in ("0", "false", "no", "off")
# Default to the original legacy dashboard so users get the old app back.
# Set TITAN_CLASSIC_APP=0 to re-enable the newer admin template/overlay UI.
_CLASSIC_APP_MODE = str(os.environ.get("TITAN_CLASSIC_APP", "1")).strip().lower() not in ("0", "false", "no", "off")


def _short_exc(exc):
    return f"{exc.__class__.__name__}: {exc}"


def _make_fallback_app(error, tb):
    try:
        from flask import Flask, jsonify, Response
    except Exception:
        raise error
    fallback = Flask(__name__)
    fallback.secret_key = os.environ.get("TITAN_FLASK_SECRET", "titan-nova-fallback")

    @fallback.route("/")
    def fallback_index():
        body = f"""<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>Titan Nova Startup Error</title><style>body{{margin:0;background:#07111d;color:#fff;font-family:Arial,sans-serif;padding:18px;line-height:1.5}}.card{{max-width:760px;margin:28px auto;border:1px solid #ff5d5d55;border-radius:18px;background:#ffffff0f;padding:18px}}pre{{white-space:pre-wrap;background:#0008;padding:12px;border-radius:12px;overflow:auto;font-size:12px}}</style></head><body><div class='card'><h2>⚠️ Titan Nova Flask startup error</h2><p><b>Error:</b> {str(error).replace('<','&lt;').replace('>','&gt;')}</p><pre>{tb[-5000:].replace('<','&lt;').replace('>','&gt;')}</pre></div></body></html>"""
        return Response(body, status=500, content_type="text/html; charset=utf-8")

    @fallback.route("/api/runtime_boot/status")
    def fallback_status():
        return jsonify({"status": "error", "version": _LAUNCHER_VERSION, "legacyLoaded": False, "startedAt": _BOOT_STARTED_AT, "legacyFile": str(_LEGACY_FILE), "error": _short_exc(error), "tracebackTail": tb[-6000:]}), 500
    return fallback


if not _LEGACY_FILE.exists():
    _LEGACY_BOOT_ERROR = FileNotFoundError(f"Missing legacy Titan Nova runtime: {_LEGACY_FILE}")
    _LEGACY_BOOT_TRACEBACK = traceback.format_exc()
    app = _make_fallback_app(_LEGACY_BOOT_ERROR, _LEGACY_BOOT_TRACEBACK)
else:
    _legacy_globals = {"__name__": "titan_legacy_runtime", "__file__": str(_LEGACY_FILE), "__package__": None}
    try:
        code = _LEGACY_FILE.read_text(encoding="utf-8")
        exec(compile(code, str(_LEGACY_FILE), "exec"), _legacy_globals, _legacy_globals)
        app = _legacy_globals.get("app")
        if app is None:
            raise RuntimeError("Titan Nova legacy runtime did not expose Flask app")
        _LEGACY_LOADED = True
    except Exception as exc:
        _LEGACY_BOOT_ERROR = exc
        _LEGACY_BOOT_TRACEBACK = traceback.format_exc()
        print("❌ Titan Nova legacy runtime failed to boot:", _short_exc(exc))
        print(_LEGACY_BOOT_TRACEBACK)
        app = _make_fallback_app(exc, _LEGACY_BOOT_TRACEBACK)


def _register_patch(label, module_name, func_name, ui_heavy=False):
    if not _LEGACY_LOADED:
        _PATCH_REPORT.append({"label": label, "module": module_name, "status": "skipped", "reason": "legacy runtime failed"})
        return
    if _CLASSIC_APP_MODE and ui_heavy:
        _PATCH_REPORT.append({"label": label, "module": module_name, "status": "skipped", "reason": "classic legacy app mode"})
        print(f"⏭️ {label} skipped in classic legacy app mode")
        return
    if _SAFE_UI_BOOT and ui_heavy:
        _PATCH_REPORT.append({"label": label, "module": module_name, "status": "skipped", "reason": "Termux safe UI boot"})
        print(f"⏭️ {label} skipped in Termux safe UI boot")
        return
    try:
        module = __import__(module_name, fromlist=[func_name])
        func = getattr(module, func_name)
        func(app)
        _PATCH_REPORT.append({"label": label, "module": module_name, "status": "loaded"})
        print(f"✅ {label} loaded")
    except Exception as exc:
        _PATCH_REPORT.append({"label": label, "module": module_name, "status": "error", "error": _short_exc(exc)})
        print(f"⚠️ {label} failed to load:", exc)


_register_patch("Finance Deposit removal guard", "finance_deposit_removed", "register_finance_deposit_removed", ui_heavy=True)
_register_patch("Titan runtime safety bridge", "deposit_finance_force", "register_deposit_finance_force", ui_heavy=True)
_register_patch("Titan global realtime/local UI guard", "titan_realtime_global", "register_titan_realtime_global", ui_heavy=True)
_register_patch("Result tab sticky toggle guard", "result_toggle_sticky", "register_result_toggle_sticky", ui_heavy=True)
_register_patch("VIP profile delete guard", "titan_profile_delete_guard_patch", "register_vip_profile_delete_guard", ui_heavy=True)
_register_patch("Deposit OCR guard", "deposit_ocr_guard", "register_deposit_ocr_guard", ui_heavy=False)
_register_patch("Strict Deposit OCR runtime", "strict_deposit_ocr_runtime", "register_strict_deposit_ocr_runtime", ui_heavy=False)
_register_patch("Titan Firebase guard", "titan_firebase_guard_patch", "register_titan_firebase_guard", ui_heavy=True)
_register_patch("Titan Setup control patch", "titan_setup_control_patch", "register_titan_setup_control", ui_heavy=True)
_register_patch("Titan Result control patch", "titan_result_control_patch", "register_titan_result_control", ui_heavy=False)
_register_patch("Titan strict result rules", "titan_strict_result_rules_patch", "register_titan_strict_result_rules", ui_heavy=False)
_register_patch("Titan frontend boot/render guard", "titan_frontend_boot_fix_patch", "register_titan_frontend_boot_fix", ui_heavy=False)
_register_patch("Titan Ledger control", "titan_ledger_control_overlay_patch", "register_titan_ledger_control_overlay", ui_heavy=False)
_register_patch("Titan VIP control patch", "titan_vip_control_patch", "register_titan_vip_control", ui_heavy=True)
_register_patch("Titan Codex stability patch", "titan_codex_stability_patch", "register_titan_codex_stability", ui_heavy=True)
_register_patch("Mobile Admin Dashboard", "titan_mobile_admin_dashboard_patch", "register_mobile_admin_dashboard", ui_heavy=True)


if _LEGACY_LOADED:
    try:
        from flask import jsonify, Response, render_template, request

        @app.route("/api/runtime_boot/status")
        def titan_runtime_boot_status():
            return jsonify({"status": "success", "version": _LAUNCHER_VERSION, "legacyLoaded": True, "classicAppMode": _CLASSIC_APP_MODE, "safeUiBoot": _SAFE_UI_BOOT, "isTermux": _IS_TERMUX, "startedAt": _BOOT_STARTED_AT, "legacyFile": str(_LEGACY_FILE), "patches": _PATCH_REPORT, "firebaseUrlConfigured": bool(os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL"))})

        @app.route("/api/plain_health")
        def titan_plain_health():
            return jsonify({"status": "success", "message": "Titan Nova Flask is responding", "classicAppMode": _CLASSIC_APP_MODE, "safeUiBoot": _SAFE_UI_BOOT})

        @app.route("/titan-test")
        def titan_test_page():
            return Response("<!doctype html><meta name='viewport' content='width=device-width'><body style='background:#07111d;color:white;font-family:Arial;padding:24px'><h2>✅ Titan Nova server working</h2><p>Flask browser response OK.</p><p><a style='color:#4ade80' href='/'>Open dashboard</a></p></body>", content_type="text/html; charset=utf-8")

        _legacy_index_view = app.view_functions.get("index")

        def titan_codex_admin_index():
            if request.args.get("vip") and _legacy_index_view:
                return _legacy_index_view()
            state_getter = _legacy_globals.get("migrate_and_get_state")
            state = state_getter() if callable(state_getter) else {}
            state["activeId"] = "admin1"
            return render_template("index.html", state=state, is_master=True)

        if not _CLASSIC_APP_MODE:
            app.view_functions["index"] = titan_codex_admin_index
    except Exception as exc:
        print("⚠️ Runtime diagnostic routes failed:", exc)


application = app

if _LAUNCHER_NAME == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000") or "5000")
    print(f"🚀 Titan Nova Flask launcher {_LAUNCHER_VERSION} on {host}:{port} legacyLoaded={_LEGACY_LOADED} classicAppMode={_CLASSIC_APP_MODE} safeUiBoot={_SAFE_UI_BOOT}")
    app.run(host=host, port=port, debug=False, threaded=True)
