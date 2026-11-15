"""Immutable speech with owner-scoped, encrypted correction projections.

Storage never receives projected text. The product read boundary projects text
for existing clients and exposes original_text alongside corrected text.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import zlib

from database import review_store
from models.agent_refs import cited_value
from models.transcript_segment import legacy_conversation_segment_id
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted, budgeted_document_get


def original_fingerprint(uid, raw, indices=None):
    from database.conversations import decode_transcript_segments_verified

    segments = decode_transcript_segments_verified(
        uid, raw.get('transcript_segments') or [], bool(raw.get('transcript_segments_compressed'))
    )
    if indices is not None:
        if any(index < 0 or index >= len(segments) for index in indices):
            raise review_store.ReviewConflict('Transcript correction anchor unavailable')
        segments = [segments[index] for index in indices]
    # Encryption can legitimately be refreshed during reprocessing. Speech and
    # its anchors are immutable; speaker labels and ciphertext are not anchors.
    return review_store.fingerprint(
        [{key: segment.get(key) for key in ('id', 'start', 'end', 'text')} for segment in segments]
    )


def preserves_correction_anchors(original_segments, incoming_segments, corrections):
    for correction in corrections:
        index = correction['segment_index']
        if index < 0 or index >= min(len(original_segments), len(incoming_segments)):
            return False
        if any(
            original_segments[index].get(field) != incoming_segments[index].get(field)
            for field in ('id', 'start', 'end', 'text')
        ):
            return False
    return True


def entries(edit, current, *, authority, change_id):
    from utils.agent_capabilities.text_edits import replace_term

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


def project(uid, conversation, *, firestore_client=None, read_budget: ListReadBudget | None = None):
    if not conversation.get('has_transcript_corrections') or 'transcript_segments' not in conversation:
        return conversation
    try:
        key = conversation.get('id')
        inline = conversation.get('transcript_correction_overlay')
        rows = (
            review_store.require_doc(uid, inline)['source']
            if inline is not None
            else load_entries(uid, key, firestore_client=firestore_client, read_budget=read_budget)
        )
        conversation['transcript_segments'] = apply_entries(conversation['transcript_segments'], rows)
        filter_projected_translations(uid, conversation)
    except ListReadBudgetExhausted:
        # A bounded recall must stop; captured speech is not a successful
        # correction projection after its read deadline has expired.
        raise
    except Exception:
        # Rendering must remain available even with stale anchors, missing or
        # corrupt encrypted data, or storage outages. Transaction writers are strict.
        from utils.dream_metrics import OVERLAY_READ_FAILURES

        OVERLAY_READ_FAILURES.inc()
        conversation['transcript_segments'] = originals(conversation['transcript_segments'])
    return conversation


def filter_projected_translations(uid, conversation):
    from database.conversations import _reveal_json_value  # pyright: ignore[reportPrivateUsage]

    try:
        raw = conversation.get('translation_materializations')
        metadata = _reveal_json_value(raw, uid, True) if raw is not None else {}
        if not isinstance(metadata, dict):
            metadata = {}
    except (ValueError, TypeError, json.JSONDecodeError, zlib.error):
        metadata = {}
    for index, segment in enumerate(conversation['transcript_segments']):
        if 'translations' not in segment:
            continue
        key = segment.get('id') or legacy_conversation_segment_id(conversation['id'], index)
        targets = metadata.get(key) or {}
        if not isinstance(targets, dict):
            targets = {}
        source = hashlib.sha256(segment.get('text', '').encode()).hexdigest()
        segment['translations'] = [
            translation
            for translation in segment.get('translations') or []
            if (
                (
                    isinstance(targets.get(translation.get('lang')), dict)
                    and targets[translation['lang']].get('source') == source
                    and targets[translation['lang']].get('translation')
                    == hashlib.sha256(translation.get('text', '').encode()).hexdigest()
                )
                or (translation.get('lang') not in targets and segment['text'] == segment['original_text'])
            )
        ]


def load_entries(uid, conversation_id, *, firestore_client=None, transaction=None, read_budget=None):
    """Owner-scoped overlay read, including use inside a source-bind transaction."""
    client = firestore_client or review_store.client()
    reference = client.collection('users').document(uid).collection('transcript_corrections').document(conversation_id)
    raw = budgeted_document_get(reference, read_budget, transaction=transaction).to_dict()
    if raw is None:
        raise review_store.ReviewConflict('Transcript correction overlay unavailable')
    rows = review_store.require_doc(uid, raw).get('source')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise review_store.ReviewConflict('Transcript correction overlay invalid')
    return rows


def apply_entries(original_segments, corrections):
    """Pure projection used at both product reads and transactional admission."""
    from utils.agent_capabilities.text_edits import replace_term

    segments = deepcopy(original_segments)
    for segment in segments:
        segment.setdefault('original_text', segment.get('text', ''))
    for correction in corrections:
        if correction['undone']:
            continue
        index = correction['segment_index']
        if index >= len(segments):
            raise review_store.ReviewConflict('Transcript correction anchor unavailable')
        segment = segments[index]
        anchors = {segment.get('id'), segment.get('segment_id')}
        if correction.get('legacy_anchor') and not segment.get('id') and not segment.get('segment_id'):
            anchors.add(legacy_conversation_segment_id(correction['conversation_id'], index))
        if correction['segment_id'] and correction['segment_id'] not in anchors:
            raise review_store.ReviewConflict('Transcript correction anchor changed')
        if segment.get('start') != correction['start']:
            raise review_store.ReviewConflict('Transcript correction anchor changed')
        if correction['kind'] == 'transcript':
            if segment.get('text', '') != correction['before']:
                raise review_store.ReviewConflict('Transcript correction input changed')
            segment['text'] = correction['after']
        else:
            segment['text'] = replace_term(segment.get('text', ''), correction['before'], correction['after'])
    return segments


def originals(segments):
    """Remove in-memory projections before any reprocessing or API persistence."""
    result = deepcopy(segments)
    for segment in result:
        original = segment.pop('original_text', None)
        if original is not None:
            segment['text'] = original
    return result
