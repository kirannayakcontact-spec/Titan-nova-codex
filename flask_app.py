# ==========================================================
# TITAN NOVA LEGACY RUNTIME LAUNCHER
# Run UI/API: python flask_app.py
# ==========================================================

from pathlib import Path
import os

# Your live Firebase. This prevents blank Ledger caused by the old compatibility
# fallback database. Env value still wins if you set FIREBASE_URL manually.
os.environ.setdefault("FIREBASE_URL", "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json")
os.environ.setdefault("FIREBASE_DB_URL", os.environ.get("FIREBASE_URL"))

_LAUNCHER_NAME = __name__
_LEGACY_FILE = Path(__file__).resolve().parent / "legacy-backup" / "flask_app.py.bak"

if not _LEGACY_FILE.exists():
    raise FileNotFoundError(f"Missing legacy Titan Nova runtime: {_LEGACY_FILE}")

_legacy_globals = {
    "__name__": "titan_legacy_runtime",
    "__file__": str(_LEGACY_FILE),
    "__package__": None,
}
code = _LEGACY_FILE.read_text(encoding="utf-8")
exec(compile(code, str(_LEGACY_FILE), "exec"), _legacy_globals, _legacy_globals)

app = _legacy_globals.get("app")
if app is None:
    raise RuntimeError("Titan Nova legacy runtime did not expose Flask app")

try:
    from finance_deposit_removed import register_finance_deposit_removed
    register_finance_deposit_removed(app)
    print("✅ Finance Deposit removal guard loaded")
except Exception as exc:
    print("⚠️ Finance Deposit removal guard failed to load:", exc)

try:
    from deposit_finance_force import register_deposit_finance_force
    register_deposit_finance_force(app)
    print("✅ Titan runtime safety bridge loaded")
except Exception as exc:
    print("⚠️ Titan runtime safety bridge failed to load:", exc)

try:
    from titan_realtime_global import register_titan_realtime_global
    register_titan_realtime_global(app)
    print("✅ Titan global realtime/local UI guard loaded")
except Exception as exc:
    print("⚠️ Titan global realtime/local UI guard failed to load:", exc)

try:
    from result_toggle_sticky import register_result_toggle_sticky
    register_result_toggle_sticky(app)
    print("✅ Result tab sticky toggle guard loaded")
except Exception as exc:
    print("⚠️ Result tab sticky toggle guard failed to load:", exc)

try:
    from titan_profile_delete_guard_patch import register_vip_profile_delete_guard
    register_vip_profile_delete_guard(app)
except Exception as exc:
    print("⚠️ VIP profile delete guard failed to load:", exc)

try:
    from deposit_ocr_guard import register_deposit_ocr_guard
    register_deposit_ocr_guard(app)
except Exception as exc:
    print("⚠️ Deposit OCR guard failed to load:", exc)

try:
    from titan_firebase_guard_patch import register_titan_firebase_guard
    register_titan_firebase_guard(app)
except Exception as exc:
    print("⚠️ Titan Firebase guard failed to load:", exc)

try:
    from titan_setup_control_patch import register_titan_setup_control
    register_titan_setup_control(app)
except Exception as exc:
    print("⚠️ Titan Setup control patch failed to load:", exc)

try:
    from titan_result_control_patch import register_titan_result_control
    register_titan_result_control(app)
except Exception as exc:
    print("⚠️ Titan Result control patch failed to load:", exc)

try:
    from titan_frontend_boot_fix_patch import register_titan_frontend_boot_fix
    register_titan_frontend_boot_fix(app)
except Exception as exc:
    print("⚠️ Titan frontend boot/render guard failed to load:", exc)

try:
    from titan_ledger_autopf_ui_patch import register_titan_ledger_autopf_ui
    register_titan_ledger_autopf_ui(app)
except Exception as exc:
    print("⚠️ Titan Ledger Auto P/F UI patch failed to load:", exc)

try:
    from titan_vip_control_patch import register_titan_vip_control
    register_titan_vip_control(app)
except Exception as exc:
    print("⚠️ Titan VIP control patch failed to load:", exc)

try:
    from titan_codex_stability_patch import register_titan_codex_stability
    register_titan_codex_stability(app)
except Exception as exc:
    print("⚠️ Titan Codex stability patch failed to load:", exc)

application = app

if _LAUNCHER_NAME == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000") or "5000")
    app.run(host=host, port=port, debug=False)
