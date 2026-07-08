# ==========================================================
# TITAN NOVA LEGACY RUNTIME LAUNCHER
# Run UI/API: python flask_app.py
#
# The full previous Titan Nova Flask runtime is preserved in:
#   legacy-backup/flask_app.py.bak
# This launcher executes that restored runtime so old Termux commands keep working.
# ==========================================================

from pathlib import Path

_LEGACY_FILE = Path(__file__).resolve().parent / "legacy-backup" / "flask_app.py.bak"

if not _LEGACY_FILE.exists():
    raise FileNotFoundError(f"Missing legacy Titan Nova runtime: {_LEGACY_FILE}")

code = _LEGACY_FILE.read_text(encoding="utf-8")
exec(compile(code, str(_LEGACY_FILE), "exec"), globals(), globals())
