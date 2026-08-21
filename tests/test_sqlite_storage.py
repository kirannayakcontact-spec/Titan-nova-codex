import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "titan_core.py").read_text()
ENV_TEMPLATE = (ROOT / "termux.env.example").read_text()


class SQLiteStorageTests(unittest.TestCase):
    def test_sqlite_is_explicit_default_and_firebase_is_opt_in(self):
        self.assertIn('TITAN_STORAGE_MODE", "sqlite"', SOURCE)
        self.assertIn('TITAN_STORAGE_MODE="sqlite"', ENV_TEMPLATE)
        self.assertIn('TITAN_STORAGE_MODE="firebase"', ENV_TEMPLATE)

    def test_sqlite_adapter_covers_root_and_child_operations(self):
        for marker in (
            "def _sqlite_load_state():",
            "def _sqlite_save_state(state, backup_label=",
            "def _sqlite_child_get(parts):",
            "def _sqlite_child_write(parts, value, mode=",
            "if _sqlite_enabled():\n        return _sqlite_load_state()",
            "if _sqlite_enabled():\n        return _sqlite_child_write(parts, value, \"put\")",
        ):
            self.assertIn(marker, SOURCE)

    def test_frontend_uses_storage_aware_notification(self):
        self.assertIn('storageMode', SOURCE)
        self.assertIn("SQLite Local Sync", SOURCE)
        self.assertNotIn("Firebase state load nahi hua ya admin token missing hai", SOURCE)

    def test_sqlite_path_is_configurable_and_not_hardcoded_to_firebase(self):
        self.assertIn("TITAN_SQLITE_PATH", SOURCE)
        self.assertIn("sqlite3.connect(TITAN_SQLITE_PATH", SOURCE)
        self.assertRegex(SOURCE, r"storageLabel.*SQLite local database")


if __name__ == "__main__":
    unittest.main()
