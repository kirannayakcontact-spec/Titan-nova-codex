import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MultiSessionArchitectureTests(unittest.TestCase):
    def manager_source(self):
        return (ROOT / "bot" / "session_manager.js").read_text()

    def gateway_source(self):
        return (ROOT / "whatsapp_multi_session.js").read_text()

    def config_source(self):
        return (ROOT / "bot" / "session_config.js").read_text()

    def routes_source(self):
        return (ROOT / "bot" / "session_routes.js").read_text()

    def access_source(self):
        return (ROOT / "bot" / "role_access.js").read_text()

    def test_all_five_roles_and_isolated_auth_path_exist(self):
        source = self.config_source() + self.manager_source()
        for role in ("owner_bot", "finance_bot", "game_bot", "result_bot", "ledger_bot"):
            self.assertIn(role, source)
        self.assertIn('path.join(this.stateDir,"auth_info_baileys",role)', source)

    def test_restricted_roles_use_sender_verification(self):
        source = self.config_source() + self.access_source() + self.manager_source().replace(" ", "")
        self.assertIn('RESTRICTED_ROLES', source)
        self.assertIn('finance_bot', source)
        self.assertIn('result_bot', source)
        self.assertIn('ledger_bot', source)
        self.assertIn("this.allowed(role,m)", source)
        self.assertIn("this.rememberMessage(role,m)", source)

    def test_gateway_event_routes_are_explicit(self):
        source = self.config_source().replace(" ", "")
        for route in ('deposit:"finance_bot"', 'withdrawal:"finance_bot"', 'game:"game_bot"',
                      'result:"result_bot"', 'ledger:"ledger_bot"', 'crash:"owner_bot"'):
            self.assertIn(route, source)

    def test_dashboard_is_guard_tab_only_and_responsive(self):
        source = (ROOT / "bot_connection_manager.py").read_text()
        self.assertIn("grid-template-columns:repeat(3,minmax(0,1fr))", source)
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr))", source)
        self.assertIn("grid-template-columns:1fr", source)
        self.assertIn("const ADMIN_TAB='admin'", source)
        self.assertIn("manager.hidden=true", source)
        self.assertIn("if(manager.parentElement!==main)main.appendChild(manager)", source)
        self.assertIn('aria-labelledby="tbcm-title" hidden', source)
        self.assertNotIn('id="tbcm-modal"', source)
        self.assertNotIn('id="tbcm-open"', source)
        self.assertIn("@app.after_request", source)

    def test_canonical_gateway_owns_legacy_webhooks_and_multi_session_routes(self):
        source = (ROOT / "whatsapp_multi_session.js").read_text()
        self.assertIn('socketInstance.ev.on("messages.upsert"', source)
        self.assertIn('require("./multi_session_manager.js")', source)
        self.assertIn("multiSessionManager.registerRoutes", source)
        self.assertIn("multiSessionManager.startAll", source)

    def test_compatibility_manager_is_only_a_module_launcher(self):
        source = (ROOT / "multi_session_manager.js").read_text()
        self.assertIn('require("./bot/session_manager.js")', source)
        self.assertNotIn("messages.upsert", source)

    def test_baileys_hooks_use_canonical_callbacks(self):
        source = self.gateway_source()
        self.assertNotIn("baileys.default =", source)
        self.assertNotIn("mod.default =", source)
        self.assertIn("__TITAN_DEPOSIT_OCR_HANDLER__", source)
        self.assertIn("__TITAN_WITHDRAWAL_HANDLER__", source)

    def test_gateway_has_process_lock_and_deploy_port_cleanup(self):
        source = self.gateway_source()
        deploy = (ROOT / "deploy.sh").read_text()
        self.assertIn("GATEWAY_LOCK_FILE", source)
        self.assertIn("kill_port_fallback", deploy)
        self.assertIn("GATEWAY_PORT", deploy)

    def test_sqlite_is_the_canonical_gateway_payment_store(self):
        gateway = self.gateway_source()
        core = (ROOT / "titan_core.py").read_text()
        self.assertIn('TITAN_STORAGE_MODE', gateway)
        self.assertIn('TITAN_SQLITE_MODE', gateway)
        self.assertIn('/api/internal/state', gateway)
        self.assertIn('/api/internal/state/child', gateway)
        self.assertIn('TITAN_SKIP_WHATSAPP_START', gateway)
        self.assertIn('handleIncomingDepositScreenshotMessage', gateway)
        self.assertIn('handleIncomingWithdrawalMessage', gateway)
        self.assertIn('/api/internal/state', core)
        self.assertIn("'storage': 'sqlite'", core)

    def test_required_boot_scripts_use_canonical_gateway(self):
        source = (ROOT / "deploy.sh").read_text()
        self.assertIn("node whatsapp_multi_session.js", source)

    def test_flask_registers_bot_manager_explicitly(self):
        source = (ROOT / "flask_app.py").read_text()
        self.assertIn("from bot_connection_manager import register_bot_connection_manager", source)
        self.assertIn("register_bot_connection_manager(app)", source)


if __name__ == "__main__":
    unittest.main()
