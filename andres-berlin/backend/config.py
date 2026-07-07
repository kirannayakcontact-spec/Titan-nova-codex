"""Configuration for the Andres Berlin backend."""

from dataclasses import dataclass
import os


def _env_float(name: str, default: float) -> float:
    """Parse a positive float from the environment."""

    try:
        value = float(os.environ.get(name, str(default)) or default)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class BackendConfig:
    """Runtime configuration resolved from environment variables."""

    app_name: str = os.environ.get("APP_NAME", "Andres Berlin")
    host: str = os.environ.get("HOST", "0.0.0.0")
    port: int = int(os.environ.get("PORT", "5000") or "5000")
    firebase_url: str = os.environ.get("FIREBASE_URL", os.environ.get("FIREBASE_DB_URL", ""))
    gateway_url: str = os.environ.get("GATEWAY_URL", "http://127.0.0.1:3000")
    admin_token: str = os.environ.get("TITAN_ADMIN_TOKEN", "")
    firebase_timeout_seconds: float = _env_float("FIREBASE_TIMEOUT_SECONDS", 2.0)
    firebase_circuit_breaker_seconds: float = _env_float("FIREBASE_CIRCUIT_BREAKER_SECONDS", 30.0)
    gateway_timeout_seconds: float = _env_float("GATEWAY_TIMEOUT_SECONDS", 2.0)


def get_config() -> BackendConfig:
    """Return a fresh configuration snapshot."""

    return BackendConfig()
