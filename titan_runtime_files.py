"""Helpers to restore Titan Nova two-file runtime from bundled backups.

The current repository keeps the legacy runtime files under ``legacy-backup/``.
Termux deploy and local patchers still operate on root-level ``flask_app.py`` and
``Gateway.js``.  This helper recreates those root files when a fresh checkout does
not have them, preventing patchers from failing with FileNotFoundError.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_RUNTIME_BACKUPS = {
    "flask_app.py": ROOT / "legacy-backup" / "flask_app.py.bak",
    "Gateway.js": ROOT / "legacy-backup" / "Gateway.js.bak",
}


def ensure_runtime_file(filename: str) -> Path:
    """Ensure a root runtime file exists, restoring it from legacy-backup if needed."""
    target = ROOT / filename
    if target.exists():
        return target

    backup = _RUNTIME_BACKUPS.get(filename)
    if backup is None:
        raise RuntimeError(f"No bundled runtime backup configured for {filename}")
    if not backup.exists():
        raise FileNotFoundError(f"Missing runtime file {target} and backup {backup}")

    shutil.copyfile(backup, target)
    print(f"Restored {filename} from {backup.relative_to(ROOT)}")
    return target


def ensure_runtime_files() -> None:
    for filename in _RUNTIME_BACKUPS:
        ensure_runtime_file(filename)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ensure", action="store_true", help="restore missing runtime files")
    parser.add_argument("files", nargs="*", help="specific runtime files to restore if missing")
    args = parser.parse_args()

    if args.files:
        for filename in args.files:
            ensure_runtime_file(filename)
    elif args.ensure:
        ensure_runtime_files()
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
