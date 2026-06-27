from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


class ConversationPhoto(BaseModel):
    id: Optional[str] = None
    base64: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    discarded: bool = False
    data_protection_level: Optional[str] = None

    @staticmethod
    def photos_as_string(photos: List['ConversationPhoto'], include_timestamps: bool = False) -> str:
        if not photos:
            return 'None'
        descriptions = []
        for p in photos:
            if p.description and p.description.strip():
                timestamp_str = ''
                if include_timestamps:
                    timestamp_str = f"[{p.created_at.strftime('%H:%M:%S')}] "
                descriptions.append(f'- {timestamp_str}"{p.description}"')

        if not descriptions:
            return 'None'
        return '\n'.join(descriptions)
