"""Flask application factory for Andres Berlin."""

from flask import Flask, jsonify, render_template_string

from backend.config import get_config
from backend.routes import register_routes
from backend.ui.templates import HOME_TEMPLATE


def create_app() -> Flask:
    """Create and configure the Flask app."""

    config = get_config()
    app = Flask(__name__)
    app.config["APP_NAME"] = config.app_name

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "app": config.app_name})

    @app.get("/")
    def home():
        return render_template_string(HOME_TEMPLATE)

    register_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    cfg = get_config()
    app.run(host=cfg.host, port=cfg.port, debug=False)
