"""Shared datetime input formats for the CLI's API-facing options."""

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
