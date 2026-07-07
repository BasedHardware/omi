"""Shared validation for messaging-connector draft requests (iMessage/Telegram/WhatsApp).

The draft `thread` can carry inline base64 images so the drafter can see shared
photos. Left unbounded, a malformed or abusive request could push an arbitrary
amount of image data through the drafter (memory + LLM token cost), and these drafts
can feed auto-reply. The desktop downscales inline photos and sends at most a couple,
so the caps below sit far above any legitimate request while still bounding the input.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

MAX_DRAFT_IMAGES = 8
MAX_IMAGE_B64_CHARS = 5_000_000  # ~3.7 MB decoded per image
# Aggregate cap across all inline images in one request. Per-image + count caps alone
# still allow 8 × 5M = 40M chars (~30 MB); this bounds the total a single request can
# push through the drafter (memory + LLM-token abuse) as defense-in-depth.
MAX_TOTAL_IMAGE_B64_CHARS = 10_000_000  # ~7.5 MB decoded across the whole request


def validate_draft_images(thread: List) -> None:
    """Raise ``ValueError`` (surfaced by FastAPI as HTTP 422) when a draft thread
    exceeds the inline-image caps. ``thread`` is a list of draft-message models, each
    exposing an optional ``image_b64`` string."""
    images = [m.image_b64 for m in (thread or []) if getattr(m, 'image_b64', None)]
    if len(images) > MAX_DRAFT_IMAGES:
        raise ValueError(f"too many inline images: {len(images)} (max {MAX_DRAFT_IMAGES})")
    for b64 in images:
        if len(b64) > MAX_IMAGE_B64_CHARS:
            raise ValueError(f"inline image too large: {len(b64)} base64 chars (max {MAX_IMAGE_B64_CHARS})")
    total = sum(len(b64) for b64 in images)
    if total > MAX_TOTAL_IMAGE_B64_CHARS:
        raise ValueError(
            f"inline images too large in aggregate: {total} base64 chars (max {MAX_TOTAL_IMAGE_B64_CHARS})"
        )


class HoldEvent(BaseModel):
    """A tentative "hold" event created on the user's Google Calendar when an
    availability-aware reply accepts a proposed time. Surfaced back to the desktop
    so the user can confirm or discard it — it is a hold, not a committed event."""

    event_id: str
    title: str
    start_time: datetime
    end_time: datetime
    html_link: Optional[str] = None
