import os
import unittest


os.environ.pop("TITAN_ADMIN_TOKEN", None)
os.environ.pop("TITAN_GATEWAY_TOKEN", None)
os.environ["TITAN_SECURITY_DISABLED"] = "0"
os.environ["TITAN_ENV"] = "production"

from flask_app import app  # noqa: E402


class DirectOpenTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health_is_open_without_token(self):
        response = self.client.get("/api/plain_health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "success")

    def test_security_status_reports_direct_open(self):
        response = self.client.get("/api/security_status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["directOpen"])
        self.assertFalse(payload["enforced"])
        self.assertFalse(payload["securityLockdown"])

    def test_admin_login_is_not_required(self):
        response = self.client.get("/")
        self.assertNotEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
