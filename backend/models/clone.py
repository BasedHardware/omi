from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from models.reply_draft import ReplyDraftLength, ReplyDraftTone

MAX_CLONE_REPLY_LENGTH = 3000
MAX_CLONE_ALTERNATIVES = 2
MAX_CLONE_SAFETY_NOTES = 5
MAX_CLONE_THREAD_MESSAGES = 40

CloneSendMode = Literal['review', 'auto']
CloneSendAction = Literal['send', 'review', 'hold']


class CloneThreadMessage(BaseModel):
    """One prior message in the conversation with this contact."""

    sender: Literal['them', 'me']
    text: str = Field(..., min_length=1, max_length=4000)

    @field_validator('text', mode='before')
    @classmethod
    def _strip(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class CloneReplyRequest(BaseModel):
    incoming_message: str = Field(..., min_length=1, max_length=4000)
    contact_id: str = Field(..., min_length=1, max_length=200)
    contact_name: Optional[str] = Field(default=None, max_length=120)
    # whatsapp / telegram / imessage / signal / instagram / ...
    network: Optional[str] = Field(default=None, max_length=40)
    relationship: Optional[str] = Field(default=None, max_length=500)
    # Recent history with this contact, oldest first.
    thread: List[CloneThreadMessage] = Field(default_factory=list, max_length=MAX_CLONE_THREAD_MESSAGES)
    goal: Optional[str] = Field(default=None, max_length=800)
    tone: ReplyDraftTone = 'natural'
    length: ReplyDraftLength = 'short'
    include_memories: bool = True
    use_persona: bool = True

    # Send policy (optional; defaults to safe review-first).
    mode: CloneSendMode = 'review'
    auto_allowlist: List[str] = Field(default_factory=list, max_length=500)
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    block_sensitive: bool = True
    quiet_hours_start: Optional[int] = Field(default=None, ge=0, le=23)
    quiet_hours_end: Optional[int] = Field(default=None, ge=0, le=23)
    # Caller's current local hour, used only for the quiet-hours check.
    local_hour: Optional[int] = Field(default=None, ge=0, le=23)

    @field_validator('incoming_message', 'contact_id', mode='before')
    @classmethod
    def _strip_required(cls, value):
        # Strip first so a whitespace-only payload becomes "" and fails min_length.
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator('contact_name', 'network', 'relationship', 'goal', mode='before')
    @classmethod
    def _strip_optional(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class CloneGeneration(BaseModel):
    """Structured LLM output for an on-behalf reply."""

    draft: str = Field(..., min_length=1, max_length=MAX_CLONE_REPLY_LENGTH)
    alternatives: List[str] = Field(default_factory=list, max_length=MAX_CLONE_ALTERNATIVES)
    safety_notes: List[str] = Field(default_factory=list, max_length=MAX_CLONE_SAFETY_NOTES)
    # Model self-reported confidence that the draft is accurate and safe to send.
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator('draft', mode='before')
    @classmethod
    def _strip_draft(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator('alternatives', 'safety_notes', mode='before')
    @classmethod
    def _strip_lists(cls, value):
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return value


class CloneContextSummary(BaseModel):
    memories_used: int
    thread_messages_used: int
    persona_used: bool


class CloneReplyResponse(BaseModel):
    draft: str = Field(..., min_length=1, max_length=MAX_CLONE_REPLY_LENGTH)
    alternatives: List[str] = Field(default_factory=list, max_length=MAX_CLONE_ALTERNATIVES)
    confidence: float = Field(..., ge=0.0, le=1.0)
    # 'send' = guardrails passed and it may be auto-sent; 'review' = draft for the
    # user to approve/edit; 'hold' = do not send now (e.g. quiet hours).
    action: CloneSendAction
    action_reason: str = Field(default='', max_length=1000)
    needs_review: bool = True
    safety_notes: List[str] = Field(default_factory=list, max_length=MAX_CLONE_SAFETY_NOTES)
    used_context: CloneContextSummary


# --- Benchmark: score the clone against the user's own past replies -----------------
# Nik's method: "benchmark it against your own past decisions" (his 10/11, ~60% match).


class CloneBenchmarkSample(BaseModel):
    incoming_message: str = Field(..., min_length=1, max_length=4000)
    actual_reply: str = Field(..., min_length=1, max_length=4000)
    contact_name: Optional[str] = Field(default=None, max_length=120)
    network: Optional[str] = Field(default=None, max_length=40)

    @field_validator('incoming_message', 'actual_reply', mode='before')
    @classmethod
    def _strip_required(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class CloneBenchmarkRequest(BaseModel):
    samples: List[CloneBenchmarkSample] = Field(..., min_length=1, max_length=50)
    use_persona: bool = True


class CloneMatchJudgment(BaseModel):
    match: bool
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ''


class CloneBenchmarkItem(BaseModel):
    incoming_message: str = Field(default='', max_length=4000)
    actual_reply: str = Field(default='', max_length=4000)
    generated_reply: str = Field(default='', max_length=MAX_CLONE_REPLY_LENGTH)
    match: bool
    score: float
    reason: str = Field(default='', max_length=2000)


class CloneBenchmarkResult(BaseModel):
    total: int
    matched: int
    # matched / total, e.g. Nik's 10/11 = 0.91.
    match_rate: float = Field(ge=0.0, le=1.0)
    average_score: float = Field(ge=0.0, le=1.0)
    items: List[CloneBenchmarkItem] = Field(default_factory=list)


# --- Personal Q&A: "omi answers personal questions very well" (Nik's #1 Track-2 bar) -----
# Answers a question ABOUT/AS the user, grounded in their memory bank ("what do you know
# about me?" comes from millions of memories, not 30 sentences).


class CloneAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    use_persona: bool = True

    @field_validator('question', mode='before')
    @classmethod
    def _strip_required(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class CloneAskGeneration(BaseModel):
    answer: str = Field(..., min_length=1, max_length=4000)
    # False when the model had to answer without support in the user's memories.
    grounded: bool = True


class CloneAskResponse(BaseModel):
    answer: str = Field(default='', max_length=4000)
    grounded: bool
    memories_used: int
    persona_used: bool
