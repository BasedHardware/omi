"""Encrypted latest decisions per stream scope, used only for rollover inheritance."""

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
    if expected_voices is None:
        return
    from utils.live_speaker_carry import voice_segments

    by_id = {s.get('id'): s for s in current['transcript_segments']}
    scoped = {
        scope: {label: {s['id'] for s in rows} for label, rows in voice_segments(current, scope).items()}
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
    """Historical scopes live in compressed transcripts; discover only within this UID."""
    from database.conversations import decode_transcript_segments_verified

    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection('conversations')
    query = collection.select(['transcript_segments', 'transcript_segments_compressed', 'deleted'])
    result = []
    for snapshot in query.stream():
        raw = snapshot.to_dict() or {}
        if raw.get('deleted'):
            continue
        segments = decode_transcript_segments_verified(
            uid, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
        )
        if any(s.get('speaker_id_scope') in scopes for s in segments):
            result.append(snapshot.id)
    return result
