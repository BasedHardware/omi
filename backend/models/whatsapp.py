from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, model_validator

from models.draft_common import HoldEvent, validate_draft_images


class WhatsAppMessage(BaseModel):
    message_id: str  # stable per-message id (ZWAMESSAGE.ZSTANZAID) from ChatStorage.sqlite, for idempotent dedup
    text: str
    is_from_me: bool
    timestamp: datetime
    # Sender identity as a canonical WhatsApp handle: the bare phone number parsed
    # from the JID (`<phone>@s.whatsapp.net`). None when is_from_me.
    handle: Optional[str] = None


class WhatsAppThread(BaseModel):
    chat_id: str  # stable WhatsApp chat id (the JID / ZCONTACTJID) used later to target replies
    display_name: Optional[str] = None  # contact name for 1:1, group title for groups
    is_group: bool = False
    messages: List[WhatsAppMessage] = []


class WhatsAppIngestRequest(BaseModel):
    threads: List[WhatsAppThread] = []
    language: Optional[str] = 'en'


class WhatsAppIngestResponse(BaseModel):
    success: bool = True
    conversations_created: int = 0
    people_upserted: int = 0
    messages_ingested: int = 0
    skipped_duplicates: int = 0
    # Durability signal for the desktop cursor: True only when EVERY window persisted
    # durably. On a partial failure the desktop must NOT advance its Z_PK cursor past
    # this batch — the failed messages released their ledger claims and would otherwise
    # never be resent. The desktop retries the whole batch; the ledger dedups the
    # windows that already landed.
    all_persisted: bool = True


class WhatsAppSettings(BaseModel):
    enabled: bool = False
    opted_out_handles: List[str] = []
    backfill_days: int = 90


class WhatsAppStatus(BaseModel):
    connected: bool = False
    enabled: bool = False
    last_synced_at: Optional[datetime] = None
    conversations_ingested: int = 0


class WhatsAppDraftMessage(BaseModel):
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


class WhatsAppDraftRequest(BaseModel):
    person: str  # name, person id, or handle (a phone number)
    thread: List[WhatsAppDraftMessage] = []
    intent: Optional[str] = None  # optional steer, e.g. "politely decline"
    is_group: bool = False  # group thread → drafter attributes senders and may abstain

    @model_validator(mode='after')
    def _bound_inline_images(self):
        validate_draft_images(self.thread)
        return self


class WhatsAppDraftResponse(BaseModel):
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


class WhatsAppContact(BaseModel):
    name: str
    handles: List[str] = []


class WhatsAppContactsSyncRequest(BaseModel):
    contacts: List[WhatsAppContact] = []


class WhatsAppContactsSyncResponse(BaseModel):
    success: bool = True
    people_upserted: int = 0
