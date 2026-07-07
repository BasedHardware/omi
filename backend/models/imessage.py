from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, model_validator

from models.draft_common import HoldEvent, validate_draft_images


class IMessageMessage(BaseModel):
    guid: str  # stable per-message id from chat.db, used for idempotent dedup
    text: str
    is_from_me: bool
    timestamp: datetime
    handle: Optional[str] = None  # normalized phone/email of the sender (None when is_from_me)


class IMessageThread(BaseModel):
    chat_guid: str  # stable Messages thread id (used later to target replies)
    chat_identifier: Optional[str] = None
    display_name: Optional[str] = None  # contact name for 1:1, group name for groups
    is_group: bool = False
    messages: List[IMessageMessage] = []


class IMessageIngestRequest(BaseModel):
    threads: List[IMessageThread] = []
    language: Optional[str] = 'en'
    last_rowid: Optional[int] = None  # desktop's chat.db high-water mark, echoed into state


class IMessageIngestResponse(BaseModel):
    success: bool = True
    conversations_created: int = 0
    people_upserted: int = 0
    messages_ingested: int = 0
    skipped_duplicates: int = 0
    # Durability signal for the desktop cursor: True only when EVERY window persisted
    # durably. On a partial failure the desktop must NOT advance its ROWID cursor past
    # this batch — the failed messages released their ledger claims and would otherwise
    # never be resent. The desktop retries the whole batch; the ledger dedups the
    # windows that already landed. (The payload carries no per-message ROWID, so the
    # safe unit of retry is the batch, not the individual message.)
    all_persisted: bool = True


class IMessageSettings(BaseModel):
    enabled: bool = False
    opted_out_handles: List[str] = []
    backfill_days: int = 90


class IMessageStatus(BaseModel):
    connected: bool = False
    enabled: bool = False
    last_synced_at: Optional[datetime] = None
    last_rowid: Optional[int] = None
    conversations_ingested: int = 0


class IMessageDraftMessage(BaseModel):
    text: str
    is_from_me: bool = False
    # In a group chat, who sent this message (display name or handle). Lets the
    # drafter attribute messages to real senders and judge whether the user is
    # actually being addressed. Ignored for 1:1 threads.
    sender: Optional[str] = None
    # Downscaled base64 JPEG of an inline photo, so the drafter can see the image.
    image_b64: Optional[str] = None
    # Optional send time; when every message in a thread carries one, draft_reply
    # sorts by it so ordering is correct regardless of client-supplied order.
    timestamp: Optional[datetime] = None


class IMessageDraftRequest(BaseModel):
    person: str  # name, person id, or handle
    thread: List[IMessageDraftMessage] = []
    intent: Optional[str] = None  # optional steer, e.g. "politely decline"
    is_group: bool = False  # group thread → drafter attributes senders and may abstain

    @model_validator(mode='after')
    def _bound_inline_images(self):
        validate_draft_images(self.thread)
        return self


class IMessageDraftResponse(BaseModel):
    draft: str
    # True when `person` matched more than one contact: `draft` then carries a
    # disambiguation ask, NOT a sendable reply. Clients must surface it and must
    # never auto-send it.
    ambiguous: bool = False
    # True when the drafter judged the latest group message wasn't directed at the
    # user: `draft` is empty and the client should show no draft.
    abstain: bool = False
    # True when the message needs the user rather than an auto-sent reply (it asks
    # something we can't answer truthfully, needs the user's decision, or requests
    # sensitive info). `draft` carries a best-guess SUGGESTION; the client must NOT
    # auto-send it — surface it for review and notify the user. `needs_input_reason`
    # is a short, user-facing explanation of why.
    needs_input: bool = False
    needs_input_reason: Optional[str] = None
    # Set when an availability-aware reply accepted a proposed time: a tentative "hold"
    # event was created on the user's Google Calendar. The client surfaces it so the user
    # can confirm or discard it. None when the reply didn't commit to a time.
    hold: Optional[HoldEvent] = None


class IMessageContact(BaseModel):
    name: str
    handles: List[str] = []


class IMessageContactsSyncRequest(BaseModel):
    contacts: List[IMessageContact] = []


class IMessageContactsSyncResponse(BaseModel):
    success: bool = True
    people_upserted: int = 0
