"""Configuration for the Andres Berlin backend."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class BackendConfig:
    """Runtime configuration resolved from environment variables."""

    app_name: str = os.environ.get("APP_NAME", "Andres Berlin")
    host: str = os.environ.get("HOST", "0.0.0.0")
    port: int = int(os.environ.get("PORT", "5000") or "5000")
    firebase_url: str = os.environ.get("FIREBASE_URL", os.environ.get("FIREBASE_DB_URL", ""))
    gateway_url: str = os.environ.get("GATEWAY_URL", "http://127.0.0.1:3000")
    gateway_timeout_seconds: float = float(os.environ.get("GATEWAY_TIMEOUT_SECONDS", "0.75") or "0.75")
    admin_token: str = os.environ.get("TITAN_ADMIN_TOKEN", "")


def get_config() -> BackendConfig:
    """Return a fresh configuration snapshot."""

    return BackendConfig()
