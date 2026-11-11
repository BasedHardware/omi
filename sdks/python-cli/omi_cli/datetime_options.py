"""Shared datetime input formats for the CLI's API-facing options."""

from datetime import datetime, timezone

# Keep Typer's original date/naive formats and accept API timestamps with
# fractions and UTC offsets. strptime's %z also accepts the UTC designator Z.
ISO_DATETIME_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S.%f",
]


def as_utc(value: datetime) -> datetime:
    """Return ``value`` on the UTC axis so naive and aware inputs stay comparable.

    The accepted formats mix naive and offset-aware timestamps, and comparing
    those directly raises ``TypeError``. Naive inputs have no offset to honor,
    so they are read as UTC — the axis the API serializes them onto.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
