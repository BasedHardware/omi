from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


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
    # Optional send time; when every message in a thread carries one, draft_reply
    # sorts by it so ordering is correct regardless of client-supplied order.
    timestamp: Optional[datetime] = None


class WhatsAppDraftRequest(BaseModel):
    person: str  # name, person id, or handle (a phone number)
    thread: List[WhatsAppDraftMessage] = []
    intent: Optional[str] = None  # optional steer, e.g. "politely decline"


class WhatsAppDraftResponse(BaseModel):
    draft: str
    # True when `person` matched more than one contact: `draft` then carries a
    # disambiguation ask, NOT a sendable reply. Clients must surface it and must
    # never auto-send it.
    ambiguous: bool = False


class WhatsAppContact(BaseModel):
    name: str
    handles: List[str] = []


class WhatsAppContactsSyncRequest(BaseModel):
    contacts: List[WhatsAppContact] = []


class WhatsAppContactsSyncResponse(BaseModel):
    success: bool = True
    people_upserted: int = 0
