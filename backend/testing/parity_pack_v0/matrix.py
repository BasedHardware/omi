"""Named synthetic overlays for the initial replay conformance matrix."""

from __future__ import annotations

from typing import Final

SYNTHETIC_MATRIX: Final[dict[str, dict[str, str]]] = {
    "baseline": {"delivery": "single", "provider": "recorded", "expected": "finalized"},
    "duplicate_delivery": {
        "delivery": "duplicate",
        "provider": "recorded",
        "expected": "idempotent",
    },
    "provider_timeout": {"delivery": "single", "provider": "timeout", "expected": "recoverable"},
    "provider_error": {"delivery": "single", "provider": "error", "expected": "failed-safe"},
    "out_of_order_events": {
        "delivery": "reordered",
        "provider": "recorded",
        "expected": "rejected",
    },
    "redacted_capture": {
        "delivery": "single",
        "provider": "recorded",
        "expected": "no-sensitive-payload",
    },
}
