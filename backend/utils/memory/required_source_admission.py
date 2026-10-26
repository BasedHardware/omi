"""Pilot-scoped owner speech admission before paid required normalization.

Explicit text keeps its separate authority. Automatic conversation evidence
must bind every quoted assertion to a confident owner segment; the full source
and original canonical item are retained when attribution is unavailable.
"""

import re

from config.refactor_modes import serving_for
from database.required_intake_fence import assert_account_active


def _normalized(text):
    return ' '.join(re.sub(r'[^\w]+', ' ', str(text).casefold()).split())


def source_revisions(uid, item, *, db_client):
    """None withholds; an empty mapping is independent explicit-text authority."""
    assert_account_active(uid, None, db_client)
    if not serving_for('SPEAKER_EVIDENCE_MODE', uid):
        return {}
    audio = [ev for ev in item.evidence if ev.conversation_id or ev.source_type == 'conversation']
    if not audio or item.user_asserted:
        return {}
    if len(audio) > 4:
        return None
    from database import conversations
    from database.conversation_revisions import firestore_revision_datetime
    from models.transcript_segment import TranscriptSegment
    from utils.conversations import owner_attribution, relevance_media_metrics
    from utils.conversations.relevance_content import exclude_from_derived

    revisions = {}
    for evidence in audio:
        source_id = evidence.conversation_id or evidence.source_id
        if not source_id or '/' in source_id:
            return None
        path = f'users/{uid}/conversations/{source_id}'
        snapshot = db_client.document(path).get()
        revision = firestore_revision_datetime(getattr(snapshot, 'update_time', None))
        raw = snapshot.to_dict()
        if not raw or revision is None:
            return None
        source = conversations.prepare_conversation_for_read(raw, uid, firestore_client=db_client)
        if (
            not source
            or source.get('deleted')
            or source.get('discarded')
            or source.get('is_locked')
            or exclude_from_derived(uid, source, consumer='memories')
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
