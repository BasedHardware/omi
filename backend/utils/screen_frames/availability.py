"""Whether screen-frame adjudication has storage and signing infrastructure."""

from __future__ import annotations

import os


def _present(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def screen_frame_storage_ready() -> bool:
    """True only when screen-frame storage and signing are provisioned."""
    if not _present("BUCKET_SCREEN_FRAMES"):
        return False
    return _present("SCREEN_FRAME_KMS_KEY") or _present("SCREEN_FRAME_SIGNING_SECRET")
