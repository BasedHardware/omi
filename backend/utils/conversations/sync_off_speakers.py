"""Apply the existing batch grouping/name policy using expiring vectors only."""

import time
import logging

from config.batch_conversation_speakers import BATCH_CONVERSATION_SCOPE
from models.conversation import ConversationSpeakers
from utils.batch_pipeline.voice_evidence import load_vectors
from utils.conversations.speaker_resolution_inputs import batch_provider_keys, manual_speakers
from utils.stt.conversation_speakers import RESOLUTION_VERSION, resolve_conversation_speakers
from utils.metrics import OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL

logger = logging.getLogger(__name__)


def resolve_sync_off(uid, conversation, receipt, deadline, load_prints, apply):
    vectors, seconds, validate = load_vectors(uid, conversation, deadline)
    if not vectors:
        conversation.speaker_resolution = ConversationSpeakers(status='unavailable', version=RESOLUTION_VERSION)
        return
    segments = conversation.transcript_segments
    keys = batch_provider_keys(segments)
    abstained = {s.id for s in segments if s.id not in keys or s.speaker_match_source == 'batch_abstention'}
    result = resolve_conversation_speakers(
        segments,
        vectors,
        manual_speakers=manual_speakers(receipt),
        voiceprints=load_prints(uid, allow_audio_repair=False),
        embedding_seconds=seconds,
        abstained_segment_ids=abstained,
        grouping='batch_authoritative',
        provider_keys=keys,
        grouping_deadline=min(deadline, time.monotonic() + 2),
    )
    if result is None:
        return
    validate()
    apply(
        conversation,
        result.speaker_ids,
        result.voice_identities,
        result.voice_identity_statuses,
        owner_voiceprint_available=result.owner_voiceprint_available,
        contradicted_segment_ids=result.contradicted_segment_ids,
        scope=f'{BATCH_CONVERSATION_SCOPE}{conversation.id}',
    )
    conversation.speaker_resolution = ConversationSpeakers(
        status='resolved' if result.coverage >= 0.9 else 'unavailable',
        version=RESOLUTION_VERSION,
        participant_speaker_ids=result.significant_speaker_ids,
    )
    # Do not export transient centroids to the durable cache/evidence producer.
    outcome = 'resolved' if result.coverage >= 0.9 else 'partial_cached'
    OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL.labels(
        outcome='resolved' if result.coverage >= 0.9 else 'partial_cached'
    ).inc()
    logger.info(
        'event=conversation_speaker_resolution source=sync_off_centroids outcome=%s voices=%d coverage=%.2f',
        outcome,
        result.stats['voices'],
        result.coverage,
    )
    return result
