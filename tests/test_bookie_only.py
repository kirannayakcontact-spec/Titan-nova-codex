import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "titan_core.py").read_text(encoding="utf-8")
GATEWAY = (ROOT / "whatsapp_multi_session.js").read_text(encoding="utf-8")
ENV = (ROOT / "termux.env.example").read_text(encoding="utf-8")


class BookieOnlyTests(unittest.TestCase):
    def test_product_is_permanently_bookie_only(self):
        self.assertIn('"payments"', CORE)
        self.assertIn('"results"', CORE)
        self.assertIn('"admin_activity"', CORE)
        self.assertNotIn("TITAN_BOOKIE_ONLY_MODE", CORE)
        self.assertNotIn("TITAN_BOOKIE_ONLY_MODE", GATEWAY)
        self.assertNotIn("TITAN_BOOKIE_ONLY_MODE", ENV)

    def test_legacy_backend_routes_are_physically_removed(self):
        removed_routes = (
            "def api_entries",
            "def api_entry_settings",
            "def api_save_entry_safety",
            "def api_bot_schedule",
            "def api_schedule_targets",
            "def api_load_forwarder",
            "def api_load_forwarder_send",
            "def api_ledger_auto_mark",
        )
        for marker in removed_routes:
            self.assertNotIn(marker, CORE)

    def test_legacy_gateway_jobs_and_entry_handler_are_removed(self):
        for marker in (
            "function scheduleTick",
            "function loadForwarderTick",
            "function handleIncomingEntryMessage",
            'managedInterval("schedule_tick"',
            'managedInterval("load_forwarder_tick"',
        ):
            self.assertNotIn(marker, GATEWAY)

    def test_auto_and_manual_result_systems_remain_active(self):
        self.assertIn('const RESULT_SCRAPE_ENABLED = String(process.env.RESULT_SCRAPE_ENABLED || "1") !== "0";', GATEWAY)
        self.assertIn('function resultScrapeTick()', GATEWAY)
        self.assertIn('managedInterval("result_scrape_tick", resultScrapeTick, RESULT_SCRAPE_INTERVAL_MS);', GATEWAY)
        self.assertIn('function runResultScrapeNow()', CORE)
        self.assertIn('function saveMarketResult(idx)', CORE)
        self.assertIn('function renderResultsTab()', CORE)
        self.assertIn('Declare', CORE)

    def test_admin_navigation_contains_only_supported_tabs(self):
        block_start = CORE.index("const navItems = [")
        block = CORE[block_start:CORE.index("navItems.forEach", block_start)]
        for tab in ("finance", "results", "audit", "guard", "clients"):
            self.assertIn("id: '" + tab + "'", block)
        for removed in ("ledger", "entries", "markets", "forward", "setup", "smart"):
            self.assertNotIn("id: '" + removed + "'", block)

    def test_termux_defaults_to_sqlite_and_auto_results(self):
        self.assertIn('export TITAN_STORAGE_MODE="sqlite"', ENV)
        self.assertIn('export RESULT_SCRAPE_ENABLED="1"', ENV)
        self.assertNotIn('export TITAN_BOOKIE_ONLY_MODE', ENV)


if __name__ == "__main__":
    unittest.main()

__all__ = ["BookieOnlyTests"]
