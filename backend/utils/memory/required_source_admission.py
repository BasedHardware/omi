"""Independent media and owner speech admission before required normalization.

Explicit text keeps its separate authority. Automatic conversation evidence
binds every quoted assertion to a confident owner segment when speaker policy
serves; media serving is independent. The full source and original canonical
item are retained when admission withholds normalization.
"""

import logging
import re

from config.refactor_modes import serving_for, shadow_or_serve, shadow_sampled
from database.required_intake_fence import assert_account_active
from database import conversations
from database.conversation_revisions import firestore_revision_datetime
from models.transcript_segment import TranscriptSegment
from utils.conversations import owner_attribution, relevance_content, relevance_media_metrics
from utils.conversations.relevance_content import FLAG
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def _normalized(text):
    return ' '.join(re.sub(r'[^\w]+', ' ', str(text).casefold()).split())


def source_revisions(uid, item, *, db_client):
    """None withholds; serving policies pin admitted source revisions."""
    assert_account_active(uid, None, db_client)
    speaker_serving = serving_for('SPEAKER_EVIDENCE_MODE', uid)
    media_serving = serving_for(FLAG, uid)
    media_observing = shadow_or_serve(FLAG) and shadow_sampled(FLAG, uid, 5.0)
    audio = [ev for ev in item.evidence if ev.conversation_id or ev.source_type == 'conversation']
    if not audio or item.user_asserted:
        return {}
    if not speaker_serving and not media_observing:
        return {}
    source_ids = {ev.conversation_id or ev.source_id for ev in audio}
    readable_ids = {source_id for source_id in source_ids if source_id and '/' not in source_id}
    if len(readable_ids) > 4:
        # Retain the existing speaker bound. Observational media work cannot
        # turn an over-budget source into a serving rejection.
        relevance_media_metrics.observe('memories', 'error')
        return None if speaker_serving or media_serving else {}

    revisions = {}
    sources = {}
    for evidence in audio:
        source_id = evidence.conversation_id or evidence.source_id
        if not source_id or '/' in source_id:
            if speaker_serving:
                return None
            continue
        path = f'users/{uid}/conversations/{source_id}'
        if path not in sources:
            try:
                snapshot = db_client.document(path).get()
                revision = firestore_revision_datetime(getattr(snapshot, 'update_time', None))
                raw = snapshot.to_dict()
                source = (
                    conversations.prepare_conversation_for_read(raw, uid, firestore_client=db_client) if raw else None
                )
            except Exception:
                if speaker_serving or media_serving:
                    raise
                # A sampled shadow read must never defer normalization.
                relevance_media_metrics.observe('memories', 'error')
                record_fallback(
                    component='other',
                    from_mode='content_kind',
                    to_mode='legacy_content',
                    reason='unavailable',
                    outcome='degraded',
                )
                logger.info('event=media_source_admission reason=source_unavailable serving=false')
                sources[path] = None, None
                continue
            sources[path] = source, revision
        source, revision = sources[path]
        if source and relevance_content.exclude_from_derived(uid, source, consumer='memories'):
            return None
        if not speaker_serving:
            # Media policy does not confer owner identity. Explicit/legacy
            # attribution keeps its authority when the speaker policy is off.
            if media_serving and source and revision is not None:
                revisions[path] = revision
            continue
        if (
            not source
            or revision is None
            or source.get('deleted')
            or source.get('discarded')
            or source.get('is_locked')
        ):
            return None
        segments = [TranscriptSegment.model_validate(row) for row in source.get('transcript_segments', [])]
        admitted = owner_attribution.confident_owner_segments(segments)
        allowed_ids = {id(segment) for segment in admitted}
        valid = bool(admitted and evidence.quote_refs)
        for quote in evidence.quote_refs:
            if quote.get('source_id') not in {None, source_id}:
                valid = False
                break
            text = _normalized(quote.get('text', ''))
            matches = [segment for segment in segments if text and f' {text} ' in f' {_normalized(segment.text)} ']
            if (
                len(matches) != 1
                or id(matches[0]) not in allowed_ids
                or (quote.get('segment_id') and quote['segment_id'] != matches[0].id)
            ):
                valid = False
                break
        relevance_media_metrics.observe_owner_memory_admission(len(segments), len(admitted) if valid else 0)
        if not valid:
            return None
        revisions[path] = revision
    return revisions
