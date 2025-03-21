# DEPRECATED: This file has been deprecated long ago
#
# This file is deprecated and should be removed. The code is not used anymore and is not referenced in any other file.
# The only file that references this file is routers/processing_memories.py, which is also deprecated.

import time
from datetime import datetime, timezone

import database.processing_memories as processing_memories_db
from database.redis_db import get_cached_user_geolocation
from models.conversation import CreateConversation, Geolocation
from models.processing_memory import ProcessingConversation, ProcessingConversationStatus, DetailProcessingConversation
from utils.conversations.location import get_google_maps_location
from utils.conversations.process_conversation import process_conversation
from utils.plugins import trigger_external_integrations


async def create_conversation_by_processing_conversation(uid: str, processing_conversation_id: str):
    # Fetch new
    processing_memories = processing_memories_db.get_processing_memories_by_id(uid, [processing_conversation_id])
    if len(processing_memories) == 0:
        print("processing conversation is not found")
        return
    processing_conversation = ProcessingConversation(**processing_memories[0])

    # Create conversation
    transcript_segments = processing_conversation.transcript_segments
    if not transcript_segments or len(transcript_segments) == 0:
        print("Transcript segments is invalid")
        return
    timer_segment_start = processing_conversation.timer_segment_start if processing_conversation.timer_segment_start else processing_conversation.timer_start
    segment_end = transcript_segments[-1].end
    new_conversation = CreateConversation(
        started_at=datetime.fromtimestamp(timer_segment_start, timezone.utc),
        finished_at=datetime.fromtimestamp(timer_segment_start + segment_end, timezone.utc),
        language=processing_conversation.language,
        transcript_segments=transcript_segments,
    )

    # Geolocation
    geolocation = get_cached_user_geolocation(uid)
    if geolocation:
        geolocation = Geolocation(**geolocation)
        new_conversation.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

    language_code = new_conversation.language
    conversation = process_conversation(uid, language_code, new_conversation)
    messages = trigger_external_integrations(uid, conversation)

    # update
    processing_conversation.memory_id = conversation.id
    processing_conversation.message_ids = list(map(lambda m: m.id, messages))
    processing_memories_db.update_processing_memory(uid, processing_conversation.id, processing_conversation.dict())

    return conversation, messages, processing_conversation


def get_processing_conversation(uid: str, id: str, ) -> DetailProcessingConversation:
    processing_conversation = processing_memories_db.get_processing_memory_by_id(uid, id)
    if not processing_conversation:
        print("processing conversation is not found")
        return
    processing_conversation = DetailProcessingConversation(**processing_conversation)

    return processing_conversation


def get_processing_memories(uid: str, filter_ids: [str] = [], limit: int = 3) -> [DetailProcessingConversation]:
    processing_conversations = []
    tracking_status = False
    if len(filter_ids) > 0:
        filter_ids = list(set(filter_ids))  # prevent duplicated wastes
        processing_conversations = processing_memories_db.get_processing_memories(uid, filter_ids=filter_ids, limit=limit)
    else:
        processing_conversations = processing_memories_db.get_processing_memories(uid, statuses=[
            ProcessingConversationStatus.Processing], limit=limit)
        tracking_status = True

    if not processing_conversations or len(processing_conversations) == 0:
        return []

    resp = [DetailProcessingConversation(**processing_conversation) for processing_conversation in processing_conversations]

    # Tracking status
    # Warn: it's suck, remove soon!
    if tracking_status:
        new_resp = []
        for pm in resp:
            # Keep processing after 5m from the capturing to, there are something went wrong.
            if pm.status == ProcessingConversationStatus.Processing and pm.capturing_to and pm.capturing_to.timestamp() < time.time() - 300:
                pm.status = ProcessingConversationStatus.Failed
                processing_memories_db.update_processing_memory_status(uid, pm.id, pm.status)
                continue
            new_resp.append(pm)
        resp = new_resp

    return resp
