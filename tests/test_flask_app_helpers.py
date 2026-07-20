import ast
from pathlib import Path
import unittest


def load_build_admin_state():
    """Load the pure helper without booting the legacy production runtime."""
    source_path = Path(__file__).parents[1] / "flask_app.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    helper = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_build_admin_state"
    )
    namespace = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace["_build_admin_state"]


class BuildAdminStateTest(unittest.TestCase):
    def setUp(self):
        self.build_admin_state = load_build_admin_state()

    def test_copies_state_before_selecting_admin(self):
        original = {"activeId": "vip1", "wallets": {"vip1": 50}}

        result = self.build_admin_state(original)

        self.assertEqual(result["activeId"], "admin1")
        self.assertEqual(original["activeId"], "vip1")
        self.assertIsNot(result, original)

    def test_recovers_when_state_is_missing_or_invalid(self):
        for state in (None, [], "unavailable"):
            with self.subTest(state=state):
                self.assertEqual(self.build_admin_state(state), {"activeId": "admin1"})


if __name__ == "__main__":
    unittest.main()
