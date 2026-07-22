from flask import Flask, jsonify

from security_runtime import register_security_runtime


def make_app():
    app = Flask(__name__)

    @app.post("/api/admin/action/<proof_id>")
    def action(proof_id):
        return jsonify(ok=True, proof_id=proof_id)

    register_security_runtime(app)
    return app


def test_security_headers_and_cors(monkeypatch):
    monkeypatch.setenv("TITAN_ALLOWED_ORIGINS", "https://console.example")
    response = make_app().test_client().post(
        "/api/admin/action/DP-123", json={}, headers={"Origin": "https://console.example"}
    )
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Access-Control-Allow-Origin"] == "https://console.example"


def test_rejects_foreign_origin_and_bad_identifier(monkeypatch):
    monkeypatch.setenv("TITAN_ALLOWED_ORIGINS", "https://console.example")
    client = make_app().test_client()
    assert client.post("/api/admin/action/ok", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/admin/action/bad%20id", json={}).status_code == 400
