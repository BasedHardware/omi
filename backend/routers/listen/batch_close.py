"""Archive barrier and metadata attachment before durable batch handoff."""

from typing import Any

from config.server_batch import has_audio, owned
from database import conversations
from database.firestore_read_metrics import FirestoreReadSite
from database.server_batch_audio import close_server_batch_audio
from utils.episodes.batch_close import attach_closed_batch_capture


async def resumable_after_drop(host: Any, conversation_id: str, row: dict | None, *, quiet_owned: bool) -> bool:
    """A phone socket drop is not a stop: the app reconnects to the same recording.

    With a quiet check owning the capture, commit this socket's audio tail without
    the close barrier and keep it open. Otherwise the caller finalizes as before.
    """
    if not (
        row
        and quiet_owned is True
        and not getattr(host.state, 'finalization_reason', None)
        and owned(row)
        and row.get('client_platform') in {'ios', 'android'}
    ):
        return False
    archive = getattr(getattr(host, 'receiver', None), 'raw_archive', None)
    if archive is not None:
        await archive.close()
    latest = await host.persistence.call(
        conversations.get_conversation,
        host.request.uid,
        conversation_id,
        read_site=FirestoreReadSite.LISTEN_RUNTIME_TEARDOWN,
    )
    return bool(latest and latest.get('status') == 'in_progress' and has_audio(latest))


async def close_batch_archive(
    host: Any, conversation_id: str, data: dict[str, Any], *, displaced: bool = False
) -> dict[str, Any] | None:
    """Seal this generation's archive and publish the close barrier.

    ``displaced`` says the caller is finalizing a generation the session has
    already left (a rollover), not the capture target it is still writing. A
    live session says nothing about whether more audio can enter a displaced
    generation, so the barrier must be published here: otherwise the row keeps
    ``server_batch_audio_received`` without ``server_batch_audio_closed`` and no
    later actor can seal it (the quiet check only closes producer rows, and the
    producer protocol is off by default).
    """
    receiver = getattr(host, 'receiver', None)
    archive = getattr(receiver, 'raw_archive', None)
    current = conversation_id == host.state.current_conversation_id
    if archive is not None and (current or displaced):
        if current:
            await archive.close()
        else:
            # The session already moved on: commit only this generation's own
            # packs, never a continuing successor's in-flight window.
            finish = getattr(archive, 'finish_recording', None)
            if finish is None:
                return data
            await finish(conversation_id)
        if (displaced or getattr(host.state, 'active', False) is not True) and not await host.persistence.call(
            close_server_batch_audio,
            host.request.uid,
            conversation_id,
            **(
                {'producer_token': host.conversations.batch_producer_token(conversation_id)}
                if getattr(getattr(host, 'conversations', None), 'batch_producer_token', None)
                else {}
            ),
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
