"""Security helper facade for backend package modules."""

import hmac


def constant_time_equal(left: str, right: str) -> bool:
    """Compare two token strings without leaking timing information."""

    return hmac.compare_digest(str(left or ""), str(right or ""))
