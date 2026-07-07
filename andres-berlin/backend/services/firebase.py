"""Firebase service facade."""

from backend.config import get_config


def firebase_status() -> dict:
    """Return Firebase configuration status without exposing secrets."""

    url = get_config().firebase_url
    return {"configured": bool(url), "urlPreview": url[:24] + "..." if url else ""}
