"""Non-null, generated first-party proactivity HTTP contract."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer


class ProactivityModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ProactivityTarget(ProactivityModel):
    kind: Literal['conversation', 'action_item']
    id: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')


class ProactivityFeedItem(ProactivityModel):
    id: str
    producer: str
    created_at: AwareDatetime
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=1000)
    target: ProactivityTarget
    acted: bool
    dismissed: bool
    feedback: Literal['none', 'thumbs_up', 'thumbs_down']

    @field_serializer('created_at')
    def serialize_time(self, value: datetime) -> str:
        return value.isoformat().replace('+00:00', 'Z')


class ProactivityFeedResponse(ProactivityModel):
    schema_version: Literal[1] = 1
    enabled: bool
    items: list[ProactivityFeedItem]
    next_cursor: str
    has_more: bool
    server_time: AwareDatetime

    @field_serializer('server_time')
    def serialize_time(self, value: datetime) -> str:
        return value.isoformat().replace('+00:00', 'Z')


class ProactivityOutcomeRequest(ProactivityModel):
    event_id: UUID
    action: Literal[
        'shown',
        'opened',
        'accepted',
        'thumbs_up',
        'replied',
        'thumbs_down',
        'producer_disabled',
        'dismissed',
        'timeout',
    ]
    surface: Literal['ios', 'android', 'macos', 'windows']
    channel: Literal['feed', 'push']


class ProactivityOutcomeResponse(ProactivityModel):
    item_id: str
    recorded: bool
    acted_24h: bool
    negative: bool
