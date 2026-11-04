"""Archive barrier and metadata attachment before durable batch handoff."""

from typing import Any

from config.server_batch import has_audio
from database import conversations
from database.firestore_read_metrics import FirestoreReadSite
from database.server_batch_audio import close_server_batch_audio
from utils.episodes.batch_close import attach_closed_batch_capture


async def close_batch_archive(host: Any, conversation_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    receiver = getattr(host, 'receiver', None)
    archive = getattr(receiver, 'raw_archive', None)
    if conversation_id == host.state.current_conversation_id and archive is not None:
        await archive.close()
        if getattr(host.state, 'active', False) is not True and not await host.persistence.call(
            close_server_batch_audio, host.request.uid, conversation_id
        ):
            return None
        data = await host.persistence.call(
            conversations.get_conversation,
            host.request.uid,
            conversation_id,
            read_site=FirestoreReadSite.LISTEN_PROCESS_CONVERSATION,
        )
        if not data:
            return None
    if data.get('server_batch_audio_closed') is True and has_audio(data):
        await host.persistence.call(attach_closed_batch_capture, host.request.uid, conversation_id, data)
    return data
