"""Resolved transcription budget shared by enforcement and the subscription snapshot."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TranscriptionAllowance:
    """The one answer to "may this user's audio be transcribed on Omi's managed STT right now?".

    ``mode`` is what the client should open: ``managed`` (Omi-billed socket),
    ``on_device`` (no managed minutes to spend — the plan's are used up, the
    subscription is not active, or the answer could not be resolved; the local
    engine is free on every plan), or ``blocked`` (the desktop trial paywall;
    nothing opens). ``remaining_seconds`` is ``None`` when the allowance is
    unlimited (unlimited plans, BYOK, reviewers), else the managed seconds
    left this month. ``reason`` is a low-cardinality label for logs and tests.
    """

    mode: str
    remaining_seconds: Optional[int]
    reason: str
    # Total managed budget, distinct from remaining after usage. None is unlimited.
    limit_seconds: Optional[int] = 0

    # Internal ladder estimate; intentionally absent from the released-client wire.
    remaining_units: Optional[float] = None
    budget_units: Optional[float] = None

    @property
    def managed(self) -> bool:
        return self.mode == 'managed'

    def as_dict(self) -> Dict[str, Any]:
        return {'mode': self.mode, 'remaining_seconds': self.remaining_seconds, 'reason': self.reason}
