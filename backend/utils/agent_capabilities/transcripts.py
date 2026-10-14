"""Immutable speech with owner-scoped, encrypted correction projections.

Storage never receives projected text. The product read boundary projects text
for existing clients and exposes original_text alongside corrected text.
"""

from copy import deepcopy
from datetime import datetime, timezone

from database import review_store
from models.agent_refs import cited_value


def original_fingerprint(uid, raw):
    from database.conversations import decode_transcript_segments_verified

    segments = decode_transcript_segments_verified(
        uid, raw.get('transcript_segments') or [], bool(raw.get('transcript_segments_compressed'))
    )
    # Encryption can legitimately be refreshed during reprocessing. Speech and
    # its anchors are immutable; speaker labels and ciphertext are not anchors.
    return review_store.fingerprint(
        [{key: segment.get(key) for key in ('id', 'start', 'end', 'text')} for segment in segments]
    )


def entries(edit, current, *, authority, change_id):
    from utils.agent_capabilities.tools import replace_term

    selected = cited_value(edit.target, {edit.target.partition('#')[0]: current}) if '#' in edit.target else None
    result = []
    for index, segment in enumerate(current.get('transcript_segments') or []):
        if '#' in edit.target and segment != selected:
            continue
        before = segment.get('text', '')
        after = replace_term(before, edit.before, edit.after)
        if before != after:
            result.append(
                {
                    'segment_id': segment.get('id') or segment.get('segment_id'),
                    'segment_index': index,
                    'start': segment.get('start'),
                    'before': edit.before,
                    'after': edit.after,
                    'kind': edit.kind,
                    'source': authority,
                    'change_id': change_id,
                    'created_at': datetime.now(timezone.utc),
                    'undone': False,
                }
            )
    return result


def project(uid, conversation, *, firestore_client=None):
    if not conversation.get('has_transcript_corrections') or 'transcript_segments' not in conversation:
        return conversation
    key = conversation.get('id')
    if not key:
        raise ValueError('Transcript projection requires a conversation id')
    client = firestore_client or review_store.client()
    raw = client.collection('users').document(uid).collection('transcript_corrections').document(key).get().to_dict()
    if raw is None:
        raise review_store.ReviewConflict('Transcript correction overlay unavailable')
    data = review_store.require_doc(uid, raw)
    segments = deepcopy(conversation['transcript_segments'])
    from utils.agent_capabilities.tools import replace_term

    for correction in data.get('source', []):
        if correction['undone']:
            continue
        index = correction['segment_index']
        if index >= len(segments):
            continue
        segment = segments[index]
        if correction['segment_id'] and correction['segment_id'] not in {segment.get('id'), segment.get('segment_id')}:
            continue
        if segment.get('start') != correction['start']:
            continue
        updated = replace_term(segment.get('text', ''), correction['before'], correction['after'])
        if updated != segment.get('text'):
            segment.setdefault('original_text', segment['text'])
            segment['text'] = updated
    conversation['transcript_segments'] = segments
    return conversation


def originals(segments):
    """Remove in-memory projections before any reprocessing or API persistence."""
    result = deepcopy(segments)
    for segment in result:
        original = segment.pop('original_text', None)
        if original is not None:
            segment['text'] = original
    return result
