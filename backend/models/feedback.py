"""Models for the unified product-feedback ledger.

Every thumbs-up/down the product collects — chat answers, floating-bar voice
answers, conversation summaries, memory keep/discard — lands in one append-only
`feedback_events` collection with a uniform envelope. Before this ledger the
four surfaces wrote three different shapes (or, for memory review, only a
mutable state field with no timestamp), so "show me yesterday's thumbs-down"
had no single query to run.

The ledger deliberately stores no message text. Chat text is encrypted at rest
per user (`utils/encryption.derive_key`), and the point of the daily report is
to make negative feedback reviewable *without* creating a second, unencrypted
copy of user conversations. The ledger and the report store pointers; the text
is decrypted on demand, per request, by the admin context endpoint.
"""

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class FeedbackSurface(str, Enum):
    """Where the rating was given. Distinct from `platform` (macOS/mobile)."""

    chat_text = 'chat_text'
    """Main-window chat (macOS) or the mobile chat page."""

    chat_voice = 'chat_voice'
    """macOS floating-bar / push-to-talk spoken answers."""

    conversation_summary = 'conversation_summary'
    """The summary Omi writes for a recorded conversation."""

    chat_notification = 'chat_notification'
    """A proactive notification card (focus/insight/task/memory) in the chat
    transcript. Kept apart from `chat_text` because rating one of these judges
    the notification, not an answer Omi gave — the same distinction #12626 drew
    for the response-quality ratio."""

    memory = 'memory'
    """A single extracted memory, kept or discarded in the memories list."""

    recording_quality = 'recording_quality'
    """Explicit quality feedback about a user-owned recording session."""


class FeedbackTargetKind(str, Enum):
    """Which collection `target_id` points into. Drives context resolution."""

    chat_message = 'chat_message'
    conversation = 'conversation'
    memory = 'memory'

    recording = 'recording'


class FeedbackReason(str, Enum):
    """Structured reason for a thumbs-down.

    The first five match the values the mobile client has always sent to
    `POST /v1/users/analytics/chat_message`; keeping them identical means the
    ledger and the legacy `analytics` rows stay comparable. The remaining five
    are desktop-only reason chips for proactive-notification cards (focus,
    insight, task, memory) — a distinct taxonomy from a chat answer's, added
    alongside the mobile five rather than folded into them so neither surface's
    categories are diluted by the other's.
    """

    too_verbose = 'too_verbose'
    incorrect_or_hallucination = 'incorrect_or_hallucination'
    not_helpful_or_irrelevant = 'not_helpful_or_irrelevant'
    didnt_follow_instructions = 'didnt_follow_instructions'
    other = 'other'

    not_about_me = 'not_about_me'
    already_done = 'already_done'
    wrong_facts = 'wrong_facts'
    bad_timing = 'bad_timing'
    not_useful = 'not_useful'


class MobileFeedbackKind(str, Enum):
    """Explicit mobile feedback surfaces with separate reason taxonomies."""

    summary_helpfulness = 'summary_helpfulness'
    recording_quality = 'recording_quality'


class MobileFeedbackReason(str, Enum):
    """Closed reasons mobile can attach to explicit output feedback.

    Reasons intentionally describe the failure mode rather than asking a
    model to classify free text.  Positive feedback can omit a reason;
    negative feedback may send one of these values only.
    """

    summary_inaccurate = 'summary_inaccurate'
    summary_incomplete = 'summary_incomplete'
    summary_irrelevant = 'summary_irrelevant'
    summary_wrong_context = 'summary_wrong_context'
    summary_other = 'summary_other'
    recording_missing_audio = 'recording_missing_audio'
    recording_poor_transcription = 'recording_poor_transcription'
    recording_wrong_speaker = 'recording_wrong_speaker'
    recording_delayed_or_stuck = 'recording_delayed_or_stuck'
    recording_fragmented_or_duplicated = 'recording_fragmented_or_duplicated'
    recording_other = 'recording_other'


SUMMARY_FEEDBACK_REASONS = frozenset(
    {
        MobileFeedbackReason.summary_inaccurate,
        MobileFeedbackReason.summary_incomplete,
        MobileFeedbackReason.summary_irrelevant,
        MobileFeedbackReason.summary_wrong_context,
        MobileFeedbackReason.summary_other,
    }
)
RECORDING_FEEDBACK_REASONS = frozenset(
    {
        MobileFeedbackReason.recording_missing_audio,
        MobileFeedbackReason.recording_poor_transcription,
        MobileFeedbackReason.recording_wrong_speaker,
        MobileFeedbackReason.recording_delayed_or_stuck,
        MobileFeedbackReason.recording_fragmented_or_duplicated,
        MobileFeedbackReason.recording_other,
    }
)


MAX_COMMENT_LENGTH = 1000


class FeedbackEvent(BaseModel):
    """One rating action, as stored. Append-only: a user who flips thumbs-down
    to thumbs-up produces a second event rather than erasing the first, because
    the moment the answer disappointed them is the thing worth reviewing."""

    id: str
    uid: str
    surface: FeedbackSurface
    target_kind: FeedbackTargetKind
    target_id: str
    value: int = Field(description='1 = thumbs up, -1 = thumbs down, 0 = rating cleared')
    created_at: datetime

    reason: Optional[FeedbackReason | MobileFeedbackReason] = None
    comment: Optional[str] = None

    platform: Optional[str] = None
    app_version: Optional[str] = None
    app_id: Optional[str] = None

    # Conversation coordinates, captured at write time so the report job never
    # has to scan a user's whole message history to find the rated turn.
    chat_session_id: Optional[str] = None
    target_created_at: Optional[datetime] = None

    # Model/prompt provenance, so a cluster of thumbs-down can be traced to a
    # prompt revision rather than guessed at.
    langsmith_run_id: Optional[str] = None
    prompt_name: Optional[str] = None
    prompt_commit: Optional[str] = None

    # Explicit mobile feedback metadata.  These values are copied only when
    # the caller supplied them or the backend already had an authoritative
    # value; missing provenance stays missing rather than becoming a guess.
    feedback_id: Optional[str] = None
    feedback_kind: Optional[MobileFeedbackKind] = None
    app_build: Optional[str] = None
    client_app_namespace: Optional[str] = None
    client_app_profile: Optional[str] = None
    backend_release: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    trace_id: Optional[str] = None
    correlation_id: Optional[str] = None
    related_conversation_id: Optional[str] = None


class MobileFeedbackRequest(BaseModel):
    """Authenticated, idempotent mobile summary/recording feedback write."""

    schema_version: Literal['mobile_feedback.v1'] = 'mobile_feedback.v1'
    feedback_id: str = Field(min_length=1, max_length=128)
    kind: MobileFeedbackKind
    # Recording-quality feedback may target either the recording-session
    # binding (the original contract) or the owning conversation when the
    # client only has the conversation coordinate. Callers should send this
    # discriminator explicitly; omission preserves legacy session semantics.
    target_kind: Optional[Literal['conversation', 'recording']] = None
    target_id: str = Field(min_length=1, max_length=256)
    value: Literal[-1, 1]
    reason: Optional[MobileFeedbackReason] = None
    comment: Optional[str] = Field(default=None, max_length=MAX_COMMENT_LENGTH)
    app_version: Optional[str] = Field(default=None, max_length=64)
    app_build: Optional[str] = Field(default=None, max_length=64)
    platform: Optional[str] = Field(default=None, max_length=32)
    client_app_namespace: Optional[str] = Field(default=None, max_length=128)
    client_app_profile: Optional[str] = Field(default=None, max_length=32)
    correlation_id: Optional[str] = Field(default=None, max_length=128)

    @field_validator('feedback_id', 'target_id')
    @classmethod
    def _trim_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError('feedback identifiers must not be blank')
        return normalized

    @model_validator(mode='after')
    def _validate_reason_surface(self) -> 'MobileFeedbackRequest':
        if self.kind is MobileFeedbackKind.summary_helpfulness and self.target_kind not in {None, 'conversation'}:
            raise ValueError('summary feedback must target a conversation')
        if self.reason is None:
            return self
        allowed = (
            SUMMARY_FEEDBACK_REASONS
            if self.kind is MobileFeedbackKind.summary_helpfulness
            else RECORDING_FEEDBACK_REASONS
        )
        if self.reason not in allowed:
            raise ValueError(f'reason {self.reason.value!r} does not belong to {self.kind.value}')
        return self


class MobileFeedbackReceipt(BaseModel):
    schema_version: Literal['mobile_feedback_receipt.v1'] = 'mobile_feedback_receipt.v1'
    feedback_id: str
    event_id: str
    created: bool
    persisted: Literal[True] = True


class MemoryUseFeedback(BaseModel):
    """Content-free receipt envelope for canonical memory-use feedback.

    The canonical apply transaction turns this envelope into one append-only
    ``FeedbackEvent``.  It lives beside the existing feedback models so the
    owner mutation and the product feedback ledger can share one idempotency
    boundary without creating a second receipt collection.
    """

    schema_version: Literal["memory_use_feedback.v1"] = "memory_use_feedback.v1"
    uid: str
    feedback_id: str = Field(min_length=1, max_length=128)
    target_memory_id: str
    action: Literal["suppress", "allow", "useful"]
    created_at: datetime

    @field_validator("uid", "feedback_id", "target_memory_id")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("memory-use feedback identifiers must not be blank")
        return normalized


class FeedbackContextTurn(BaseModel):
    """A pointer to one turn near the rated one. Carries no text."""

    message_id: str
    sender: str
    created_at: datetime
    chat_session_id: Optional[str] = None
    position: str = Field(description="'before', 'rated', or 'after'")
    seconds_from_rated: int = Field(
        description='Signed offset from the rated turn. Negative is before.',
    )


class FeedbackContextPointer(BaseModel):
    """The resolved context window for one negative event — ids only."""

    event_id: str
    uid: str
    target_kind: FeedbackTargetKind
    target_id: str
    turns: List[FeedbackContextTurn] = []
    follow_up_count: int = 0
    follow_up_window_seconds: int = 0
    truncated_before: bool = False
    """True when the session had more preceding turns than the cap allowed."""
    truncated_after: bool = False
    """True when more turns followed inside the window than the cap allowed.

    The window promises *every* follow-up within its five minutes, so a silent
    cut would misreport a busy retry burst as a short one."""
    resolution_error: Optional[str] = None
    """Set when the window could not be built (deleted message, etc.)."""


class FeedbackReportEntry(BaseModel):
    """One thumbs-down in a daily report."""

    event: FeedbackEvent
    context: FeedbackContextPointer


class FeedbackReport(BaseModel):
    """A materialized daily report. Pointers only — no conversation text."""

    date: str = Field(description='UTC calendar date, YYYY-MM-DD')
    generated_at: datetime
    total_negative: int
    counts_by_surface: dict[str, int] = {}
    counts_by_reason: dict[str, int] = {}
    counts_by_platform: dict[str, int] = {}
    entries: List[FeedbackReportEntry] = []
    truncated: bool = False
    """True when the day held more negative events than this report carries —
    because the entry cap, the raw-row fetch bound, or the Firestore document
    size budget cut it short. `total_negative` still counts the whole day."""


class FeedbackContextTurnText(BaseModel):
    """A hydrated turn: pointer plus the decrypted text. Never persisted."""

    message_id: str
    sender: str
    created_at: datetime
    position: str
    seconds_from_rated: int
    text: str


class FeedbackContextHydrated(BaseModel):
    """On-demand decryption result for one event's context window."""

    event_id: str
    target_kind: FeedbackTargetKind
    target_id: str
    turns: List[FeedbackContextTurnText] = []
    unavailable: List[str] = []
    """Message ids that could not be read back: deleted since the report ran, or
    still encrypted because the decrypt did not succeed. Listing the id is the
    honest answer — showing a ciphertext blob as if it were the user's words is
    not."""
