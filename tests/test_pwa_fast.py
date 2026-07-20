import unittest

from flask import Flask, Response

from titan_pwa_fast_patch import PWA_VERSION, register_titan_pwa_fast


class FastPwaPatchTest(unittest.TestCase):
    def make_app(self):
        app = Flask(__name__)

        @app.get("/")
        def index():
            return "<!doctype html><html><head></head><body>Titan</body></html>"

        @app.get("/sw.js")
        def old_worker():
            return Response("old worker", content_type="application/javascript")

        register_titan_pwa_fast(app)
        return app

    def test_injects_client_once(self):
        client = self.make_app().test_client()
        body = client.get("/").get_data(as_text=True)
        self.assertEqual(body.count('data-titan-pwa-fast="1"'), 1)
        self.assertIn("/static/pwa-fast.js", body)

    def test_replaces_worker_and_disables_http_cache(self):
        client = self.make_app().test_client()
        response = client.get("/sw.js")
        body = response.get_data(as_text=True)
        self.assertIn("Never replay or cache writes", body)
        self.assertIn(PWA_VERSION, response.headers["X-Titan-PWA-Version"])
        self.assertEqual(response.headers["Cache-Control"], "no-cache, no-store, must-revalidate")


if __name__ == "__main__":
    unittest.main()
