from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field
from pydantic import field_validator


class ConversationPhoto(BaseModel):
    id: Optional[str] = None
    # Legacy captures carry inline pixels.  Conversation-lifetime frame
    # evidence carries an opaque GCS reference instead; ambient pixels never
    # enter this model.
    base64: str
    storage_id: Optional[str] = None
    content_type: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    discarded: bool = False
    data_protection_level: Optional[str] = None

    @field_validator('storage_id')
    @classmethod
    def validate_storage_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value or '/' in value or '\\' in value or value.startswith(('http:', 'https:')):
            raise ValueError('storage_id must be an opaque owner-scoped identifier')
        return value

    @field_validator('content_type')
    @classmethod
    def validate_content_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip().lower()
        if not value.startswith('image/') or len(value) > 100:
            raise ValueError('content_type must be an image media type')
        return value

    @staticmethod
    def photos_as_string(photos: List['ConversationPhoto'], include_timestamps: bool = False) -> str:
        if not photos:
            return 'None'
        descriptions: list[str] = []
        for p in photos:
            if p.description and p.description.strip():
                timestamp_str = ''
                if include_timestamps:
                    timestamp_str = f"[{p.created_at.strftime('%H:%M:%S')}] "
                descriptions.append(f'- {timestamp_str}"{p.description}"')

        if not descriptions:
            return 'None'
        return '\n'.join(descriptions)
