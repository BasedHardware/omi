import json
import logging
from typing import Any, Optional
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# FCM rejects any message whose `data` payload exceeds 4KB, and it rejects the
# whole message — an oversized card would take the daily summary down with it,
# so the push would silently never arrive. `content_blocks` is the only
# variable-size entry in the payload; the rest (id, timestamps, a body already
# truncated to 150 chars, a deep link) is comfortably under 1KB. Bound the card
# below that headroom and drop it if it does not fit: losing the card costs a
# render, losing the message costs the recap.
MAX_CONTENT_BLOCKS_BYTES = 3000


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
            encoded = json.dumps(message.content_blocks, ensure_ascii=False)
            if len(encoded.encode('utf-8')) > MAX_CONTENT_BLOCKS_BYTES:
                logger.warning(
                    'notification_content_blocks_dropped type=%s bytes=%d limit=%d',
                    message.type,
                    len(encoded.encode('utf-8')),
                    MAX_CONTENT_BLOCKS_BYTES,
                )
                del message_dict['content_blocks']
            else:
                message_dict['content_blocks'] = encoded
        else:
            del message_dict['content_blocks']

        return message_dict
