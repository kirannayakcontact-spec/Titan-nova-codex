"""Node gateway integration helpers."""

from backend.config import get_config


def gateway_status() -> dict:
    """Return gateway configuration status."""

    return {"status": "configured", "gatewayUrl": get_config().gateway_url}
