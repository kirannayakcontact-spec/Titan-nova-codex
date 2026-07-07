"""Firebase client facade placeholder for package-based backend code.

The legacy implementation is still centralized in ``flask_app.py``. New backend
services can depend on this module as the future home for Firebase access logic.
"""

from backend.config import get_config


def firebase_url() -> str:
    """Return the configured Firebase database URL, if any."""

    return get_config().firebase_url
