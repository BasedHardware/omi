from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class WebhookSigningSecretIssuedResponse(BaseModel):
    """Returned once, when a secret is issued or rotated; the secret is never readable again."""

    secret: str
    created_at: datetime
    previous_valid_until: Optional[datetime] = None


class WebhookSigningSecretStatusResponse(BaseModel):
    configured: bool
    created_at: Optional[datetime] = None
    previous_valid_until: Optional[datetime] = None


class WebhookSigningSecretDeletedResponse(BaseModel):
    status: str
