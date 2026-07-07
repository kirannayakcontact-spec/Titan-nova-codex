"""Security helpers for Andres Berlin."""

import hmac


def constant_time_equal(left: str, right: str) -> bool:
    """Compare strings without leaking timing information."""

    return hmac.compare_digest(str(left or ""), str(right or ""))
