import re
from datetime import datetime
from email.utils import parsedate_to_datetime

# ... [existing imports and non-relevant code] ...

def _parse_retry_after(value: str) -> float | None:
    """Parse Retry-After header into seconds, per RFC 9110 §10.2.3."""
    if not value:
        return None
    cleaned = value.strip()

    # RFC 9110 delay-seconds uses ASCII digits, not Python float syntax.
    if re.fullmatch(r'^[0-9]+$', cleaned):
        return float(cleaned)

    try:
        dt = parsedate_to_datetime(cleaned)
        if dt:
            return (dt - datetime.now()).total_seconds()
    except (TypeError, ValueError, OverflowError):
        pass

    return None