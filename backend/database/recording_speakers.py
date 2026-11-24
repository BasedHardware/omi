"""Bounded recording discovery, scoped assignments, and encrypted rollover decisions."""

import hashlib
import json

from database._client import get_firestore_client
from utils.encryption import decrypt, encrypt


def _ref(client, uid, scope):
    key = hashlib.sha256(scope.encode()).hexdigest()
    return client.collection('users').document(uid).collection('recording_speaker_decisions').document(key)


def read(uid, scope):
    row = _ref(get_firestore_client(), uid, scope).get().to_dict() or {}
    return json.loads(decrypt(row['content'], uid)) if row.get('content') else {}


def prepare(transaction, client, uid, conversation, expected_voices, decided_at):
    """Read before side-effect writes; return encrypted documents to stage last."""
    from utils.live_speaker_carry import carried_receipt

    writes = []
    scopes = {voice[0] for voice in (expected_voices or {}).values() if voice is not None and voice[0]}
    for scope in scopes:
        ref = _ref(client, uid, scope)
        row = ref.get(transaction=transaction).to_dict() or {}
        decisions = json.loads(decrypt(row['content'], uid)) if row.get('content') else {}
        labels = {voice[1] for voice in expected_voices.values() if voice is not None and voice[0] == scope}
        for entry in (carried_receipt(conversation, scope).get('speakers') or {}).values():
            label = entry['stream_speaker']
            if label in labels and decided_at >= decisions.get(label, {}).get('decided_at', ''):
                decisions[label] = dict(entry, decided_at=decided_at)
        writes.append((ref, {'content': encrypt(json.dumps(decisions), uid)}))
    return writes


def validate_selection(current, expected_voices):
    """Fence stale ids and scope joins once per voice, before any transaction writes."""
    from utils.live_speaker_carry import voice_segments
    from utils.manual_speaker_assignments import assignment_segments

    from utils.conversations.fragment_visibility import is_relevance_discarded

    if is_relevance_discarded(current) or current.get('deleted'):
        raise ValueError('Selected conversation is no longer visible')
    if expected_voices is None:
        return
    normalized = dict(current, transcript_segments=assignment_segments(current))
    by_id = {s.get('id'): s for s in normalized['transcript_segments']}
    scoped = {
        scope: {label: {s['id'] for s in rows} for label, rows in voice_segments(normalized, scope).items()}
        for scope in {voice[0] for voice in expected_voices.values() if voice is not None and voice[0]}
    }
    for sid, voice in expected_voices.items():
        if sid not in by_id:
            raise ValueError('Selected speaker changed; select the lines again')
        if voice is not None:
            scope, label = voice
            matches = by_id[sid].get('speaker_id') == label if scope is None else sid in scoped[scope].get(label, set())
            if not matches:
                raise ValueError('Selected speaker changed; select the lines again')


def prepare_assignment(
    transaction, client, uid, current, segments, receipt, expected_voices, decided_at, recording_voice_defaults
):
    if expected_voices:
        from utils.manual_speaker_assignments import recording_voice_key

        receipt['voices'] = dict(receipt.get('voices') or {})
        by_id = {s['id']: s for s in segments}
        for sid, voice in expected_voices.items():
            if voice is None:
                continue
            if voice[0] is None:
                if recording_voice_defaults and not by_id[sid].get('speaker_id_scope'):
                    receipt.setdefault('speakers', {})[str(by_id[sid]['speaker_id'])] = dict(
                        receipt['segments'][sid],
                        source='recording_legacy',
                        speaker_id_scope=None,
                    )
                continue
            scope, label = voice
            receipt['segments'][sid]['decided_at'] = decided_at
            receipt['segments'][sid]['source'] = 'recording' if recording_voice_defaults else 'recording_segment'
            if not recording_voice_defaults:
                continue
            receipt['voices'][recording_voice_key(scope, label)] = dict(
                receipt['segments'][sid],
                source='recording',
                stream_speaker=label,
                decided_at=decided_at,
                speaker_id=by_id[sid]['speaker_id'],
            )
        if not receipt['voices']:
            receipt.pop('voices', None)
    return (
        prepare(
            transaction,
            client,
            uid,
            dict(current, transcript_segments=segments, manual_speaker_assignments=receipt),
            expected_voices,
            decided_at,
        )
        if expected_voices
        else []
    )


def scope_conversation_ids(uid, scopes, *, firestore_client=None):
    """Bounded UID-local candidates, including hidden ids so coverage cannot omit them."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    from config.recording_speakers import MAX_MEMBERS, MAX_SCOPES, SCOPE_INDEX_FIELD, check_budget

    if len(scopes) > MAX_SCOPES:
        check_budget(MAX_MEMBERS + 1)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection('conversations')
    query = collection.where(filter=FieldFilter(SCOPE_INDEX_FIELD, 'array_contains_any', sorted(scopes)))
    snapshots = list(query.select(['deleted', 'discarded', 'is_locked']).limit(MAX_MEMBERS + 1).stream())
    check_budget(len(snapshots))
    return [s.id for s in snapshots]


def legacy_recording_conversation_ids(uid, origin_id, *, firestore_client=None):
    """Bounded origin lookup plus the first generation's pre-origin session stamp.

    Session ids rotate on rollover, so session equality alone cannot establish
    complete recording coverage. Retain hidden ids as evidence of exclusions.
    """
    from google.cloud.firestore_v1.base_query import FieldFilter
    from config.recording_speakers import MAX_MEMBERS, check_budget

    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection('conversations')
    candidates = {}
    for field in ('recording_origin_id', 'recording_session_id'):
        query = collection.where(filter=FieldFilter(f'external_data.{field}', '==', origin_id))
        snapshots = list(query.select(['deleted', 'discarded', 'is_locked']).limit(MAX_MEMBERS + 1).stream())
        check_budget(len(snapshots))
        for snapshot in snapshots:
            candidates[snapshot.id] = snapshot.to_dict() or {}
        check_budget(len(candidates))
    return list(candidates)


def same_assignment(transaction, client, uid, current, expected_voices, intent):
    """A retry of an already committed decision earns no new receipt or learning job."""
    if not expected_voices:
        return False
    from utils.manual_speaker_assignments import recording_voice_key

    person_id, is_user, training, defaults = intent
    receipt = current.get('manual_speaker_assignments') or {}
    by_id = {s.get('id'): s for s in current.get('transcript_segments') or []}

    def same(entry):
        return bool(entry) and (
            entry.get('person_id') == person_id
            and bool(entry.get('is_user')) == is_user
            and entry.get('use_for_speech_training', True) == training
            and not entry.get('rejection')
        )

    scopes = {}
    for sid, (scope, label) in expected_voices.items():
        entry = (receipt.get('segments') or {}).get(sid) or {}
        line = by_id.get(sid) or {}
        if not same(entry) or line.get('person_id') != person_id or bool(line.get('is_user')) != is_user:
            return False
        if not defaults:
            if scope and entry.get('source') != 'recording_segment':
                return False
            continue
        default = (
            (receipt.get('voices') or {}).get(recording_voice_key(scope, label))
            if scope
            else (receipt.get('speakers') or {}).get(str(label))
        )
        if not same(default):
            return False
        if scope:
            scopes.setdefault(scope, set()).add(label)
    for scope, labels in scopes.items():
        row = _ref(client, uid, scope).get(transaction=transaction).to_dict() or {}
        decisions = json.loads(decrypt(row['content'], uid)) if row.get('content') else {}
        if any(not same(decisions.get(label)) for label in labels):
            return False
    # Repair only this successfully validated row, including no-op retries.
    # This metadata write creates no receipt generation or learning job.
    from config.recording_speakers import SCOPE_INDEX_FIELD, stamp_scope_index

    indexed = {'transcript_segments': current.get('transcript_segments') or []}
    stamp_scope_index(indexed)
    if current.get(SCOPE_INDEX_FIELD) != indexed[SCOPE_INDEX_FIELD]:
        ref = client.collection('users').document(uid).collection('conversations').document(current['id'])
        transaction.update(ref, {SCOPE_INDEX_FIELD: indexed[SCOPE_INDEX_FIELD]})
    return True
