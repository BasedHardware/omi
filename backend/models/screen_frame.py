"""Wire types and internal models for meeting-note screenshot egress.

Mirror these exactly in Swift (Lane B) and TS (Lane C) — see
`data/reports/meeting-screenshots/DESIGN-sol.md` for rationale, and the
authoritative contract at the time this was written for the exact shapes.

The one property that must not be broken: the client never decides what may
be stored. It uploads candidate bytes; the server canonicalises them, judges
those exact bytes, mints an internal approval, and only a holder of that
approval may write to the screenshot bucket. `ScreenFrameApprovalClaims` is
never serialized into any response model — it does not leave the process.
"""

from __future__ import annotations

import unicodedata

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScreenFrameEgressPurpose(str, Enum):
    MEETING_NOTE_V1 = "meeting_note_v1"


class ScreenFrameRetentionClass(str, Enum):
    WITH_SUBJECT = "with_subject"


# ---------------------------------------------------------------------------
# Request wire types
# ---------------------------------------------------------------------------


class ScreenFrameSubjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["conversation"]
    id: str = Field(min_length=1, max_length=256)


class ScreenFrameCandidateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_frame_id: str = Field(min_length=1, max_length=128)
    captured_at: datetime
    mime_type: Literal["image/jpeg", "image/png"]
    declared_width: int = Field(ge=1, le=10000)
    declared_height: int = Field(ge=1, le=10000)
    sha256_base64: str = Field(min_length=44, max_length=44)  # transport check only
    bytes_base64: str


class ScreenFrameAdjudicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    attempt_id: UUID
    purpose: Literal["meeting_note_v1"]
    subject: ScreenFrameSubjectIn
    candidates: List[ScreenFrameCandidateIn] = Field(min_length=1, max_length=8)


class ScreenFrameSharingUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class ScreenFrameSettings(BaseModel):
    """The account-level setting gating screen-frame egress admission
    (contract §6, setting_key="meeting_note_screenshots_enabled"). Shared and
    authoritative across every device — desktop, web, a reinstall — because
    it protects the user from themselves (accidentally leaving the feature
    on), not third parties from the user; the privacy judge is what protects
    people appearing in frames. It does not need to be tamper-proof, only
    consistent, so it is a plain user-profile field, not a signed claim.
    """

    model_config = ConfigDict(extra="forbid")

    meeting_note_screenshots_enabled: bool


class ScreenFrameSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_note_screenshots_enabled: bool


# ---------------------------------------------------------------------------
# Stored / response wire types
# ---------------------------------------------------------------------------


class NormalizedRect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    width: float
    height: float


class ScreenFrameGround(BaseModel):
    """Gradient stops derived from the canonical bytes at approval time.

    Both clients render the banner from these; neither samples pixels. A
    signed cross-origin URL cannot be read back from a canvas (no guaranteed
    CORS headers), and two independent extractions (Swift on macOS, JS on
    web) would drift from each other anyway. Extracted once, server-side,
    from the canonical JPEG — see utils/screen_frames/palette.py, a port of
    desktop/macos/Desktop/Sources/MeetingScreenshots/MeetingBannerPalette.swift.
    """

    model_config = ConfigDict(extra="forbid")

    stops: List[str] = Field(min_length=2, max_length=2)  # "#RRGGBB"
    is_neutral: bool


class ConversationScreenFrame(BaseModel):
    id: str
    captured_at: datetime
    role: Literal["banner", "strip"]
    rank: int = Field(ge=0, le=6)
    caption: str = Field(max_length=160)
    labels: List[str] = Field(max_length=8)
    source_badge: Optional[Literal["code", "browser", "document", "slides", "product"]] = None
    focal_region: Optional[NormalizedRect] = None
    width: int
    height: int
    content_url: str  # signed, 60 min
    thumbnail_url: str  # signed, 60 min
    url_expires_at: datetime
    ground: ScreenFrameGround


class ConversationScreenFrameSet(BaseModel):
    revision: int
    banner: Optional[ConversationScreenFrame] = None
    strip: List[ConversationScreenFrame] = Field(default_factory=list, max_length=6)
    adjudicated_at: Optional[datetime] = None
    """When an adjudication pass last ran, whatever it decided.

    A client must use this, not `revision`, to decide whether to offer candidates. `revision`
    only moves when something was approved, so an all-rejected pass leaves it at 0 and reads as
    "never attempted" — and the client then re-uploads the very frames the judge refused, on
    every reopen. Those are the sensitive ones by definition.
    """


class ScreenFrameAdjudicationResponse(BaseModel):
    attempt_id: UUID
    outcome: Literal["committed", "no_approved_frames"]
    frame_set: ConversationScreenFrameSet


# ---------------------------------------------------------------------------
# The judge's strict discriminated output (§4 steps 3-4 of the contract).
#
# There is deliberately NO separate decision+sensitivity pair: the measured
# judge produced contradictory sensitive+publish verdicts twice
# (FINDINGS.md:100-108). A single discriminated outcome cannot contradict
# itself the way two independent fields can.
# ---------------------------------------------------------------------------


_JOINERS = "\u200d\u200c\ufe0f\ufe0e"


class ScreenFrameJudgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["approved_clean", "rejected"]
    reject_reason: Optional[
        Literal[
            "credentials",
            "private_messages",
            "email",
            "banking",
            "medical",
            "identifiable_person",
            "personal_document",
            "unreadable",
            "other",
        ]
    ] = None
    # Deliberately NOT max_length/max_items constrained, unlike the wire model above.
    # Vertex treats a responseSchema's maxLength as advisory, so gemini-2.5-flash-lite
    # overruns it in normal use (measured 2026-08-25: one caption in seven came back
    # over 160 chars) even though the prompt states the limit too. A strict constraint
    # here does not shorten the caption — it raises inside .with_structured_output(),
    # which judge_frame() turns into judge_call_failed, and the frame is dropped. That
    # trades a cosmetic overrun for silently losing a frame the judge approved, with no
    # safety benefit: caption and labels are descriptive metadata and carry no part of
    # the verdict. So normalise instead, and let the wire model keep the real contract.
    caption: str
    labels: List[str]
    source_badge: Optional[Literal["code", "browser", "document", "slides", "product"]] = None
    banner_suitability: float = Field(ge=0, le=1)

    @field_validator("caption", mode="before")
    @classmethod
    def _truncate_caption(cls, value: object) -> object:
        if not isinstance(value, str) or len(value) <= 160:
            return value
        # A plain [:160] can cut inside a grapheme cluster and leave a dangling
        # zero-width joiner or combining mark, which every client then renders as
        # a broken glyph. Back off to the last codepoint that can end a string.
        cut = value[:160]
        while cut and (unicodedata.combining(cut[-1]) or cut[-1] in _JOINERS):
            cut = cut[:-1]
        return cut

    @field_validator("labels", mode="before")
    @classmethod
    def _cap_labels(cls, value: object) -> object:
        return value[:8] if isinstance(value, list) else value


# ---------------------------------------------------------------------------
# The internal approval object. This NEVER appears in a response model and is
# never sent to a client — see module docstring.
# ---------------------------------------------------------------------------


class ScreenFrameApprovalClaims(BaseModel):
    iss: Literal["omi-screen-frame-adjudicator"]
    aud: Literal["omi-screen-frame-writer"]
    jti: UUID  # one-use
    uid: str
    purpose: str
    subject_kind: Literal["conversation"]
    subject_id: str
    canonical_sha256: str
    model: str
    policy_version: str
    prompt_version: str
    retention: str
    decision: Literal["approved_clean"]
    labels_digest: str
    issued_at: datetime
    expires_at: datetime  # <= 10 minutes
