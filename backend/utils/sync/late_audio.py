"""Already-transcribed late listen audio uses the ordinary temporal sync intake.

No live target is inferred from the socket carrying a historical batch. The
same assignment index, privacy fences, retries, hold and enrichment outbox as
WAL intake own the recording. Original audio custody remains with listen/WAL.
"""

from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from models.conversation import CreateConversation
from models.conversation_enums import ConversationStatus
from utils.conversations import lifecycle
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
from utils.conversations.recorded_time import recorded_span
from utils.enrichment import outbox
from utils.sync import processing_hold


def ingest_late_transcript(uid: str, row: dict, segments: list[dict]) -> dict:
    from utils.episodes.finalize import schedule_synced_intake_attach

    span = recorded_span(row.get('started_at'), segments)
    if span is None:
        raise ValueError('late transcript has no recorded span')
    incoming = {
        key: deepcopy(row[key])
        for key in (
            'source',
            'client_device_id',
            'client_platform',
            'is_locked',
            'private_cloud_sync_enabled',
            'language',
            'geolocation',
            'data_protection_level',
        )
        if key in row
    }
    # Stable across a lost reply, independent of the live rollover generation.
    identity = '|'.join(sorted(str(s.get('id') or '') for s in segments))
    incoming.update(
        id=str(uuid5(NAMESPACE_URL, f'late-listen:{uid}:{span[0].isoformat()}:{identity}')),
        started_at=span[0],
        finished_at=span[1],
        created_at=span[0],
        status=ConversationStatus.completed,
        transcript_segments=deepcopy(segments),
    )
    shift = (span[0] - row['started_at']).total_seconds()
    for segment in incoming['transcript_segments']:
        segment['start'] -= shift
        segment['end'] -= shift
        segment.setdefault('speaker_id_scope', f'late-listen:{row["id"]}')
        segment.setdefault('is_user', False)
    minimum = CreateConversation(**incoming)
    incoming['structured'] = build_deterministic_minimum_structured(minimum, uid=uid).model_dump()
    assigned, _, _ = lifecycle.ingest_sync_conversation(uid, incoming)
    # Mark on retries too: a crash after assignment must not strand enrichment.
    outbox.mark(uid, assigned['id'], assigned.get('language') or 'en', sync_hold=processing_hold.enabled())
    schedule_synced_intake_attach(uid, assigned['id'], assigned)
    return assigned
