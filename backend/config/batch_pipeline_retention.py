"""Shared staged-audio lifecycle and safe input-expiry margins; no runtime IO."""

LIFECYCLE_DAYS = 60
LIFECYCLE_SECONDS = LIFECYCLE_DAYS * 86400
WARNING_SECONDS = (LIFECYCLE_DAYS - 9) * 86400
TERMINAL_SECONDS = (LIFECYCLE_DAYS - 1) * 86400
