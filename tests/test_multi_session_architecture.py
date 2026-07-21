import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MultiSessionArchitectureTests(unittest.TestCase):
    def test_all_five_roles_and_isolated_auth_path_exist(self):
        source = (ROOT / "whatsapp_multi_session.js").read_text()
        for role in ("owner_bot", "finance_bot", "game_bot", "result_bot", "ledger_bot"):
            self.assertIn(role, source)
        self.assertIn('path.join(this.stateDir,"auth_info_baileys",role)', source)

    def test_restricted_roles_use_sender_verification(self):
        source = (ROOT / "whatsapp_multi_session.js").read_text()
        self.assertIn('restricted = new Set(["finance_bot", "result_bot", "ledger_bot"])', source)
        self.assertIn("if(isCommand&&!this.allowed(role,m)) continue", source)

    def test_gateway_event_routes_are_explicit(self):
        source = (ROOT / "whatsapp_multi_session.js").read_text()
        for route in ('deposit:"finance_bot"', 'withdrawal:"finance_bot"', 'game:"game_bot"',
                      'result:"result_bot"', 'ledger:"ledger_bot"', 'crash:"owner_bot"'):
            self.assertIn(route, source)

    def test_dashboard_is_additive_and_responsive(self):
        source = (ROOT / "bot_connection_manager.py").read_text()
        self.assertIn("display:flex;flex-wrap:wrap", source)
        self.assertIn("calc(33.333% - 12px)", source)
        self.assertIn("calc(50% - 12px)", source)
        self.assertIn("@app.after_request", source)


if __name__ == "__main__":
    unittest.main()
