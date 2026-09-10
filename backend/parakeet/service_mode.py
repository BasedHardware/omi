"""Runtime mode contract for the Parakeet GPU service.

The image is shared by the batch and realtime deployments, but a GPU pod must
load only the model family it serves.  ``mixed`` preserves the historical
single-process behavior for deployments that do not set the mode explicitly.
"""

from __future__ import annotations

from typing import Mapping

SERVICE_MODE_ENV = "PARAKEET_SERVICE_MODE"
DEFAULT_SERVICE_MODE = "mixed"
VALID_SERVICE_MODES = ("mixed", "batch", "stream")


def get_service_mode(env: Mapping[str, str]) -> str:
    """Return the normalized service mode or fail closed on bad configuration."""

    mode = env.get(SERVICE_MODE_ENV, DEFAULT_SERVICE_MODE).strip().lower()
    if mode not in VALID_SERVICE_MODES:
        allowed = ", ".join(VALID_SERVICE_MODES)
        raise ValueError(f"{SERVICE_MODE_ENV} must be one of {allowed}, got '{mode}'")
    return mode
