import time
from datetime import datetime, timezone

import database.processing_memories as processing_memories_db
from database.redis_db import get_cached_user_geolocation
from models.memory import CreateMemory, Geolocation
from models.processing_memory import ProcessingMemory, ProcessingMemoryStatus, DetailProcessingMemory
from utils.memories.location import get_google_maps_location
from utils.memories.process_memory import process_memory
from utils.plugins import trigger_external_integrations


async def create_memory_by_processing_memory(uid: str, processing_memory_id: str):
    # Fetch new
    processing_memories = processing_memories_db.get_processing_memories_by_id(uid, [processing_memory_id])
    if len(processing_memories) == 0:
        print("processing memory is not found")
        return
    processing_memory = ProcessingMemory(**processing_memories[0])

    # Create memory
    transcript_segments = processing_memory.transcript_segments
    if not transcript_segments or len(transcript_segments) == 0:
        print("Transcript segments is invalid")
        return
    timer_segment_start = processing_memory.timer_segment_start if processing_memory.timer_segment_start else processing_memory.timer_start
    segment_end = transcript_segments[-1].end
    new_memory = CreateMemory(
        started_at=datetime.fromtimestamp(timer_segment_start, timezone.utc),
        finished_at=datetime.fromtimestamp(timer_segment_start + segment_end, timezone.utc),
        language=processing_memory.language,
        transcript_segments=transcript_segments,
    )

    # Geolocation
    geolocation = get_cached_user_geolocation(uid)
    if geolocation:
        geolocation = Geolocation(**geolocation)
        new_memory.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

    language_code = new_memory.language
    memory = process_memory(uid, language_code, new_memory)
    messages = trigger_external_integrations(uid, memory)

    # update
    processing_memory.memory_id = memory.id
    processing_memory.message_ids = list(map(lambda m: m.id, messages))
    processing_memories_db.update_processing_memory(uid, processing_memory.id, processing_memory.dict())

    return memory, messages, processing_memory


def get_processing_memory(uid: str, id: str, ) -> DetailProcessingMemory:
    processing_memory = processing_memories_db.get_processing_memory_by_id(uid, id)
    if not processing_memory:
        print("processing memory is not found")
        return
    processing_memory = DetailProcessingMemory(**processing_memory)

    return processing_memory


def get_processing_memories(uid: str, filter_ids: [str] = [], limit: int = 3) -> [DetailProcessingMemory]:
    processing_memories = []
    tracking_status = False
    if len(filter_ids) > 0:
        filter_ids = list(set(filter_ids))  # prevent duplicated wastes
        processing_memories = processing_memories_db.get_processing_memories(uid, filter_ids=filter_ids, limit=limit)
    else:
        processing_memories = processing_memories_db.get_processing_memories(uid, statuses=[
            ProcessingMemoryStatus.Processing], limit=limit)
        tracking_status = True

    if not processing_memories or len(processing_memories) == 0:
        return []

    resp = [DetailProcessingMemory(**processing_memory) for processing_memory in processing_memories]

    # Tracking status
    # Warn: it's suck, remove soon!
    if tracking_status:
        new_resp = []
        for pm in resp:
            # Keep processing after 5m from the capturing to, there are something went wrong.
            if pm.status == ProcessingMemoryStatus.Processing and pm.capturing_to and pm.capturing_to.timestamp() < time.time() - 300:
                pm.status = ProcessingMemoryStatus.Failed
                processing_memories_db.update_processing_memory_status(uid, pm.id, pm.status)
                continue
            new_resp.append(pm)
        resp = new_resp

    return resp
