import json
from typing import Any, Optional
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class NotificationMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    sender: str = Field(default='ai')
    plugin_id: Optional[str] = None
    from_integration: str
    type: str
    notification_type: str
    text: Optional[str] = ""
    navigate_to: Optional[str] = None
    # Structured chat content blocks for the message the client materializes
    # from this push. Same block vocabulary as `models.chat.Message.content_blocks`.
    content_blocks: Optional[list[dict[str, Any]]] = None

    @staticmethod
    def get_message_as_dict(
        message: 'NotificationMessage',
    ) -> dict[str, object]:

        message_dict = message.model_dump()

        # Remove 'plugin_id' if it is None
        if message.plugin_id is None:
            del message_dict['plugin_id']

        if message.navigate_to is None:
            del message_dict['navigate_to']

        # FCM data payloads are Dict[str, str]: a nested list would make the whole
        # batch send fail. Structured payloads travel as JSON text, the same shape
        # `utils.notifications` already uses for batched action items.
        if message.content_blocks:
            message_dict['content_blocks'] = json.dumps(message.content_blocks, ensure_ascii=False)
        else:
            del message_dict['content_blocks']

        return message_dict
