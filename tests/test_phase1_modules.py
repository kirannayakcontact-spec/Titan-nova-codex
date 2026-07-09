"""Import checks for Phase 1 modular scaffold."""

from backend.config import load_backend_config, startup_warnings
from backend.health import build_backend_health


def test_backend_config_import_safe():
    cfg = load_backend_config()
    assert cfg.firebase_url.endswith(".json")
    assert isinstance(startup_warnings(cfg), list)


def test_backend_health_import_safe():
    health = build_backend_health()
    assert health["runtime"]["entrypoint"] == "flask_app.py"
    assert health["runtime"]["behaviorChanged"] is False
