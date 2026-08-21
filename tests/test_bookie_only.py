import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "titan_core.py").read_text(encoding="utf-8")
GATEWAY = (ROOT / "whatsapp_multi_session.js").read_text(encoding="utf-8")
ENV = (ROOT / "termux.env.example").read_text(encoding="utf-8")


class BookieOnlyTests(unittest.TestCase):
    def test_bookie_mode_is_default_and_exposes_core_modules(self):
        self.assertIn('TITAN_BOOKIE_ONLY_MODE', CORE)
        self.assertIn('"bookieOnlyMode": TITAN_BOOKIE_ONLY_MODE', CORE)
        self.assertIn('"payments"', CORE)
        self.assertIn('"results"', CORE)
        self.assertIn('"admin_activity"', CORE)

    def test_non_bookie_flask_routes_are_guarded(self):
        self.assertIn('BOOKIE_DISABLED_ROUTE_RE', CORE)
        for marker in ('ledger', 'schedule', 'entries', 'scrape', 'market_source_scan', 'load'):
            self.assertIn(marker, CORE)
        self.assertIn('feature": "bookie_only_mode"', CORE)
        self.assertIn('}), 410', CORE)

    def test_gateway_disables_non_bookie_jobs(self):
        self.assertIn('const TITAN_BOOKIE_ONLY_MODE', GATEWAY)
        self.assertIn('if(!TITAN_BOOKIE_ONLY_MODE) managedInterval("schedule_tick"', GATEWAY)
        self.assertIn('if(!TITAN_BOOKIE_ONLY_MODE) managedInterval("result_scrape_tick"', GATEWAY)
        self.assertIn('if(!TITAN_BOOKIE_ONLY_MODE) managedInterval("load_forwarder_tick"', GATEWAY)
        self.assertIn('ledger_bot:()=>false', GATEWAY)
        self.assertIn('if(TITAN_BOOKIE_ONLY_MODE) return false;', GATEWAY)

    def test_manual_result_publisher_remains_without_scrape_controls(self):
        self.assertIn('renderBookieResultsTab', CORE)
        self.assertIn('Manual WhatsApp Result System', CORE)
        self.assertIn('saveMarketResult', CORE)
        self.assertNotIn('runResultScrapeNow()', CORE[CORE.index('function renderBookieResultsTab'):CORE.index('function renderResultsTab')])

    def test_bookie_only_dashboard_nav_has_core_tabs(self):
        block = CORE[CORE.index('const navItems = TITAN_BOOKIE_ONLY_MODE'):CORE.index('if(IS_MASTER && !TITAN_BOOKIE_ONLY_MODE)')]
        for tab in ("finance", "results", "audit", "guard", "clients"):
            self.assertIn("id: '" + tab + "'", block)
        for removed in ("id: 'entries'", "id: 'markets'", "id: 'forward'"):
            self.assertNotIn(removed, block)

    def test_termux_defaults_to_bookie_only(self):
        self.assertIn('export TITAN_BOOKIE_ONLY_MODE="1"', ENV)
        self.assertIn('export RESULT_SCRAPE_ENABLED="0"', ENV)


if __name__ == '__main__':
    unittest.main()

__all__ = ["BookieOnlyTests"]

# Keep the module small and deterministic; no network or WhatsApp login is required.
_ = re.compile(r"TITAN_BOOKIE_ONLY_MODE")
_ = os.environ.get("TITAN_BOOKIE_ONLY_MODE", "1")
