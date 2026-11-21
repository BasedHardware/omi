"""Pure identity shared by calendar persistence and async selection reads."""

from hashlib import sha256


def account_key(primary_calendar_id: str) -> str:
    return sha256(primary_calendar_id.encode()).hexdigest()
