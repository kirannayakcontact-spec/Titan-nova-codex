# ==========================================================
# TITAN NOVA LEGACY RUNTIME LAUNCHER
# Run UI/API: python flask_app.py
# ==========================================================

from pathlib import Path
import os
import traceback
import time

# Your live Firebase. This prevents blank Ledger caused by the old compatibility
# fallback database. Env value still wins if you set FIREBASE_URL manually.
os.environ.setdefault("FIREBASE_URL", "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json")
os.environ.setdefault("FIREBASE_DB_URL", os.environ.get("FIREBASE_URL"))

_LAUNCHER_NAME = __name__
_LAUNCHER_VERSION = "2026-07-10-flask-startup-diagnostic-v1"
_BASE_DIR = Path(__file__).resolve().parent
_LEGACY_FILE = _BASE_DIR / "legacy-backup" / "flask_app.py.bak"
_BOOT_STARTED_AT = time.strftime("%Y-%m-%dT%H:%M:%S%z")
_PATCH_REPORT = []
_LEGACY_BOOT_ERROR = None
_LEGACY_BOOT_TRACEBACK = ""
_LEGACY_LOADED = False


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
        body = f"""
<!doctype html>
<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Titan Nova Startup Error</title>
<style>body{{margin:0;background:#07111d;color:#fff;font-family:Arial,system-ui,sans-serif;padding:18px;line-height:1.5}}.card{{max-width:760px;margin:28px auto;border:1px solid rgba(255,93,93,.35);border-radius:18px;background:rgba(255,255,255,.06);padding:18px}}pre{{white-space:pre-wrap;background:#0008;padding:12px;border-radius:12px;overflow:auto;font-size:12px}}code{{background:#0008;padding:2px 5px;border-radius:6px}}</style>
</head><body><div class='card'>
<h2>⚠️ Titan Nova Flask startup error</h2>
<p>Flask server open ho gaya, lekin legacy dashboard load nahi hua. Ye page diagnostic fallback hai.</p>
<p><b>Error:</b> <code>{str(error).replace('<','&lt;').replace('>','&gt;')}</code></p>
<p>Termux me ye command run karke full log bhejo:</p>
<pre>cd ~/Titan-nova-codex 2&gt;/dev/null || cd ~/titan-app
bash termux_diagnose.sh</pre>
<p>Status endpoint: <code>/api/runtime_boot/status</code></p>
<pre>{tb[-5000:].replace('<','&lt;').replace('>','&gt;')}</pre>
</div></body></html>
"""
        return Response(body, status=500, content_type="text/html; charset=utf-8")

    @fallback.route("/api/runtime_boot/status")
    def fallback_status():
        return jsonify({
            "status": "error",
            "version": _LAUNCHER_VERSION,
            "legacyLoaded": False,
            "startedAt": _BOOT_STARTED_AT,
            "legacyFile": str(_LEGACY_FILE),
            "error": _short_exc(error),
            "tracebackTail": tb[-6000:],
            "firebaseUrlConfigured": bool(os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL")),
        }), 500

    return fallback


if not _LEGACY_FILE.exists():
    _LEGACY_BOOT_ERROR = FileNotFoundError(f"Missing legacy Titan Nova runtime: {_LEGACY_FILE}")
    _LEGACY_BOOT_TRACEBACK = traceback.format_exc()
    app = _make_fallback_app(_LEGACY_BOOT_ERROR, _LEGACY_BOOT_TRACEBACK)
else:
    _legacy_globals = {
        "__name__": "titan_legacy_runtime",
        "__file__": str(_LEGACY_FILE),
        "__package__": None,
    }
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


def _register_patch(label, module_name, func_name):
    if not _LEGACY_LOADED:
        _PATCH_REPORT.append({"label": label, "module": module_name, "status": "skipped", "reason": "legacy runtime failed"})
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


_register_patch("Finance Deposit removal guard", "finance_deposit_removed", "register_finance_deposit_removed")
_register_patch("Titan runtime safety bridge", "deposit_finance_force", "register_deposit_finance_force")
_register_patch("Titan global realtime/local UI guard", "titan_realtime_global", "register_titan_realtime_global")
_register_patch("Result tab sticky toggle guard", "result_toggle_sticky", "register_result_toggle_sticky")
_register_patch("VIP profile delete guard", "titan_profile_delete_guard_patch", "register_vip_profile_delete_guard")
_register_patch("Deposit OCR guard", "deposit_ocr_guard", "register_deposit_ocr_guard")
_register_patch("Titan Firebase guard", "titan_firebase_guard_patch", "register_titan_firebase_guard")
_register_patch("Titan Setup control patch", "titan_setup_control_patch", "register_titan_setup_control")
_register_patch("Titan Result control patch", "titan_result_control_patch", "register_titan_result_control")
_register_patch("Titan frontend boot/render guard", "titan_frontend_boot_fix_patch", "register_titan_frontend_boot_fix")
_register_patch("Titan Ledger Auto P/F UI patch", "titan_ledger_autopf_ui_patch", "register_titan_ledger_autopf_ui")
_register_patch("Titan VIP control patch", "titan_vip_control_patch", "register_titan_vip_control")
_register_patch("Titan Codex stability patch", "titan_codex_stability_patch", "register_titan_codex_stability")


if _LEGACY_LOADED:
    try:
        from flask import jsonify

        @app.route("/api/runtime_boot/status")
        def titan_runtime_boot_status():
            return jsonify({
                "status": "success",
                "version": _LAUNCHER_VERSION,
                "legacyLoaded": True,
                "startedAt": _BOOT_STARTED_AT,
                "legacyFile": str(_LEGACY_FILE),
                "patches": _PATCH_REPORT,
                "firebaseUrlConfigured": bool(os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL")),
                "firebaseUrlTail": str(os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL") or "")[-90:],
            })
    except Exception as exc:
        print("⚠️ Runtime boot status route failed:", exc)


application = app

if _LAUNCHER_NAME == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000") or "5000")
    print(f"🚀 Titan Nova Flask launcher {_LAUNCHER_VERSION} on {host}:{port} legacyLoaded={_LEGACY_LOADED}")
    app.run(host=host, port=port, debug=False)
