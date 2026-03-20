from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ShareSpeechProfileRequest(BaseModel):
    recipient_user_id: Optional[str] = Field(
        default=None, description="Recipient's Omi user ID"
    )
    recipient_email: Optional[str] = Field(
        default=None, description="Recipient's email address"
    )
    display_name: str = Field(
        ..., min_length=1, max_length=100, description="Label for this speaker"
    )

    @model_validator(mode="after")
    def require_one_identifier(self) -> "ShareSpeechProfileRequest":
        if not self.recipient_user_id and not self.recipient_email:
            raise ValueError(
                "Provide either recipient_user_id or recipient_email"
            )
        return self


class RevokeSpeechProfileRequest(BaseModel):
    recipient_user_id: str = Field(..., description="Recipient's Omi user ID")


class SharedProfileResponse(BaseModel):
    sharer_uid: str
    display_name: str
    created_at: datetime
    sharer_display_name: Optional[str] = None
