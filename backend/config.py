"""Configuration helpers for Titan Nova backend modules."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BackendConfig:
    """Runtime configuration resolved from environment variables."""

    firebase_url: str = os.environ.get("FIREBASE_URL", os.environ.get("FIREBASE_DB_URL", ""))
    admin_token: str = os.environ.get("TITAN_ADMIN_TOKEN", "")
    gateway_url: str = os.environ.get("GATEWAY_URL", "http://127.0.0.1:3000")
    app_timezone: str = os.environ.get("APP_TZ", "Asia/Kolkata")


def get_config() -> BackendConfig:
    """Return the current backend configuration snapshot."""

    return BackendConfig()
