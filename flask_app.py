# ==========================================================
# TITAN NOVA LEGACY RUNTIME LAUNCHER + DEPOSIT PROFESSIONAL V2
# Run UI/API: python flask_app.py
#
# The full previous Titan Nova Flask runtime is preserved in:
#   legacy-backup/flask_app.py.bak
# This launcher executes that restored runtime, then loads small upgrade modules
# before starting Flask.
# ==========================================================

from pathlib import Path
import os

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
    from deposit_professional_v2 import register_deposit_professional_v2
    register_deposit_professional_v2(app, _legacy_globals)
    print("✅ Titan Deposit Professional V2 loaded")
except Exception as exc:
    print("⚠️ Titan Deposit Professional V2 failed to load:", exc)

try:
    from deposit_finance_merge import register_deposit_finance_merge
    register_deposit_finance_merge(app)
    print("✅ Titan Deposit merged into Finance tab")
except Exception as exc:
    print("⚠️ Titan Deposit Finance merge failed to load:", exc)

application = app

if _LAUNCHER_NAME == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000") or "5000")
    app.run(host=host, port=port, debug=False)
