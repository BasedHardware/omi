"""Contract for the capture coverage ledger (refactor lane L1; listen side L4).

One authority answers "has this stretch of audio already been transcribed into a
conversation?". Positions are S1 source-frame ordinals within a capture key, never
wall clock and never speaker labels.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

CoverageOrigin = Literal['live', 'sync', 'batch', 'desktop', 'import']
AdmitBasis = Literal['frames', 'text_fallback', 'unknown']


class CaptureKey(BaseModel):
    """Identifies one capture stream; the same fields as S1 ``CaptureEvidenceMetadata``."""

    capture_root: str
    channel: str = 'default'
    clock_epoch: str = 'default'
    device_id: Optional[str] = None
    recording_session_id: Optional[str] = None


class FrameRange(BaseModel):
    start: int = Field(ge=0)
    end: int  # exclusive; end > start

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)


class CoverageRecord(BaseModel):
    conversation_id: str
    origin: CoverageOrigin
    ranges: List[FrameRange]


class AdmitResult(BaseModel):
    """What an intake path may transcribe: only ``uncovered``. ``basis`` says how it was decided."""

    uncovered: List[FrameRange]
    covered: List[FrameRange] = []
    covering_conversation_id: Optional[str] = None
    basis: AdmitBasis = 'unknown'


class CaptureCommittedEvent(BaseModel):
    """Listen transcript receipt with optional generation-pinned original audio evidence."""

    type: Literal['capture_committed'] = 'capture_committed'
    conversation_id: str
    capture_root: str
    channel: str = 'default'
    clock_epoch: str = 'default'
    recording_session_id: Optional[str] = None
    source_start: int
    source_end: int
    audio_custody: Optional[dict] = Field(default=None, exclude=True)

    def to_json(self):
        wire = self.model_dump(mode='json')
        if self.audio_custody is not None:
            wire['audio_custody'] = self.audio_custody
        return wire
