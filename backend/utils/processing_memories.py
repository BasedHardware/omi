import uuid
from datetime import datetime

from models.processing_memory import ProcessingMemory
from models.memory import Memory, PostProcessingModel, PostProcessingStatus, MemoryPostProcessing, TranscriptSegment
from utils.memories.process_memory import process_memory
from utils.memories.location import get_google_maps_location
from utils.plugins import trigger_external_integrations
import database.processing_memories as processing_memories_db
import database.memories as memories_db


async def create_memory_by_processing_memory(uid: str, processing_memory_id: str):
    # Fetch new
    processing_memories = processing_memories_db.get_processing_memories_by_id(uid, [processing_memory_id])
    if len(processing_memories) == 0:
        print("processing memory is not found")
        return
    processing_memory = ProcessingMemory(**processing_memories[0])

    # Create memory
    transcript_segements = processing_memory.transcript_segments
    timer_start = processing_memory.timer_start
    segment_end = transcript_segements[len(transcript_segements)-1]["end"]
    new_memory = Memory(
        id=str(uuid.uuid4()),
        uid=uid,
        started_at=datetime.fromtimestamp(timer_start),
        finished_at=datetime.fromtimestamp(timer_start + segment_end),
        language=processing_memory.language,
    )
    transcript_segments = transcript_segements
    if not transcript_segments or len(transcript_segments) == 0:
        print("Transcript segments is invalid")
        return
    new_memory.transcript_segments = map(lambda m: TranscriptSegment(**m), transcript_segments)

    geolocation = processing_memory.geolocation
    if geolocation and not geolocation.google_place_id:
        new_memory.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

    language_code = new_memory.language
    memory = process_memory(uid, language_code, new_memory)

    if not memory.discarded:
        memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.not_started)
        memory.postprocessing = MemoryPostProcessing(status=PostProcessingStatus.not_started,
                                                     model=PostProcessingModel.fal_whisperx)

    messages = trigger_external_integrations(uid, memory)

    # update
    processing_memory.message_ids = map(lambda m: m.id, messages)
    processing_memories_db.update_processing_memory(uid, processing_memory.id, processing_memory.dict())

    return memory
