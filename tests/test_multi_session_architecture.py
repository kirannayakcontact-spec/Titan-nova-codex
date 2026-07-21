import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MultiSessionArchitectureTests(unittest.TestCase):
    def manager_source(self):
        return (ROOT / "multi_session_manager.js").read_text()

    def test_all_five_roles_and_isolated_auth_path_exist(self):
        source = self.manager_source()
        for role in ("owner_bot", "finance_bot", "game_bot", "result_bot", "ledger_bot"):
            self.assertIn(role, source)
        self.assertIn('path.join(this.stateDir,"auth_info_baileys",role)', source)

    def test_restricted_roles_use_sender_verification(self):
        source = self.manager_source()
        self.assertIn('restricted = new Set(["finance_bot", "result_bot", "ledger_bot"])', source)
        self.assertIn("if(isCommand&&!this.allowed(role,m)) continue", source)

    def test_gateway_event_routes_are_explicit(self):
        source = self.manager_source()
        for route in ('deposit:"finance_bot"', 'withdrawal:"finance_bot"', 'game:"game_bot"',
                      'result:"result_bot"', 'ledger:"ledger_bot"', 'crash:"owner_bot"'):
            self.assertIn(route, source)

    def test_dashboard_is_additive_and_responsive(self):
        source = (ROOT / "bot_connection_manager.py").read_text()
        self.assertIn("display:flex;flex-wrap:wrap", source)
        self.assertIn("calc(33.333% - 12px)", source)
        self.assertIn("calc(50% - 12px)", source)
        self.assertIn("@app.after_request", source)

    def test_canonical_gateway_owns_legacy_webhooks_and_multi_session_routes(self):
        source = (ROOT / "whatsapp_multi_session.js").read_text()
        self.assertIn('socketInstance.ev.on("messages.upsert"', source)
        self.assertIn('require("./multi_session_manager.js")', source)
        self.assertIn("multiSessionManager.registerRoutes", source)
        self.assertIn("multiSessionManager.startAll", source)

    def test_legacy_gateway_is_only_a_compatibility_launcher(self):
        source = (ROOT / "Gateway.js").read_text()
        self.assertIn('require("./whatsapp_multi_session.js")', source)
        self.assertNotIn("messages.upsert", source)

    def test_required_boot_scripts_use_canonical_gateway(self):
        for filename in ("termux-gateway.sh", "deploy.sh"):
            source = (ROOT / filename).read_text()
            self.assertIn("node whatsapp_multi_session.js", source)
        flask_source = (ROOT / "termux-flask.sh").read_text()
        self.assertIn('export GATEWAY_URL=', flask_source)

    def test_flask_registers_bot_manager_explicitly(self):
        source = (ROOT / "flask_app.py").read_text()
        self.assertIn("from bot_connection_manager import register_bot_connection_manager", source)
        self.assertIn("register_bot_connection_manager(app)", source)


if __name__ == "__main__":
    unittest.main()
