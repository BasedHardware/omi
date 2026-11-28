"""Daily-recap row predicates shared by the recap job and the recap API."""

from datetime import datetime, timezone


def delivery_allowed(uid, payload):
    """A durable pending/failed stub is never proof that the model finished."""
    return payload.get('status') in (None, 'generated')


def finish_legacy_stub(existing, payload):
    """An earlier status row is completed in place when the recap is regenerated."""
    if existing and existing.get('status') is not None:
        return {**payload, 'status': 'generated', 'generated_at': datetime.now(timezone.utc)}
    return payload
