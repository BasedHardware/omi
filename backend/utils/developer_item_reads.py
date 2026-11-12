"""Authorized developer conversation detail reads, including bounded 404 reuse.

The router resolves auth, scope and query validation before this helper.
Transcript grant checks still precede cache reads. Source behavior and audit
outcomes stay shared by origin and cache paths.
"""

from fastapi import HTTPException
from typing import Any, Callable
from utils import external_polling_cache as polling_cache
from utils.conversations import transcribing_hold


def read_conversation_item(
    conversation_id: str,
    include_transcript: bool,
    auth: Any,
    request: Any,
    *,
    conversations_db: Any,
    cache_client: Callable[[], Any],
    check_transcript: Callable[..., Any],
    populate_speaker_names: Callable[..., Any],
    populate_folder_names: Callable[..., Any],
    audit: Callable[..., Any],
) -> dict[str, Any]:
    uid = auth.uid
    status = 500
    returned_count = None
    try:
        if include_transcript:
            check_transcript(auth, request=request)

        negative_key = polling_cache.negative_key(request, uid, auth, conversation_id)
        if negative_key and polling_cache.missing(cache_client(), negative_key):
            raise HTTPException(
                404,
                detail='Conversation ID not found or unknown conversation sub-route',
                headers={'X-Omi-List-Cache': 'negative; max-age=10'},
            )
        conversation = conversations_db.get_conversation(uid, conversation_id)
        if conversation is None and negative_key:
            polling_cache.remember_missing(cache_client(), negative_key)
        if not conversation or conversation.get('deleted', False):
            status = 404
            returned_count = 0
            raise HTTPException(status_code=404, detail="Conversation ID not found or unknown conversation sub-route")

        # Filter out locked conversations
        if conversation.get('is_locked', False):
            status = 404
            returned_count = 0
            raise HTTPException(status_code=404, detail="Conversation ID not found or unknown conversation sub-route")

        from utils.mcp_server.helpers import conversation_participants

        conversation.update(conversation_participants(conversation, include_display=False))
        conversation['transcript_included'] = include_transcript

        conversation = transcribing_hold.project(conversation)

        # Remove transcript_segments if not requested
        if not include_transcript:
            conversation.pop('transcript_segments', None)
        else:
            populate_speaker_names(uid, [conversation], preserve_api_values=True)

        populate_folder_names(uid, [conversation])

        status = 200
        returned_count = 1
        return conversation
    except HTTPException as e:
        status = e.status_code
        returned_count = 0 if returned_count is None else returned_count
        raise
    finally:
        audit(
            request=request,
            auth=auth,
            operation='get_conversation',
            status=status,
            include_transcript=include_transcript,
            returned_count=returned_count,
            resource_id=conversation_id,
        )
