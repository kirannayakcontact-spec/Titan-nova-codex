"""Firebase client facade placeholder for package-based backend code.

New backend services should use the modular helpers in ``andres-berlin/backend``
instead of adding duplicate compatibility logic here.
"""

from backend.config import get_config


def firebase_url() -> str:
    """Return the configured Firebase database URL, if any."""

    return get_config().firebase_url
