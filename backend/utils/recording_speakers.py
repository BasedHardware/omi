"""Explicit naming across a recording; never joins embeddings or different scopes.

Episode membership is authoritative when present. The non-episode compatibility
path scans this user's stored rows because historical transcripts have no
queryable scope index. No timestamps or conversation-local speaker ids join rows.
"""

from datetime import datetime, timezone

from database import conversations as conversations_db, episodes as episodes_db
from database._client import get_firestore_client
from models.transcript_segment import TranscriptSegment
from models.recording_speakers import RecordingSpeakerRequest
from utils.stt.speaker_identity import canonical_speaker_label
from utils.live_speaker_carry import carried_receipt, voice_segments
from utils.manual_speaker_assignments import manual_assignment
from utils.speaker_assignment_teaching import commit_manual_assignment
from utils.observability.fallback import record_fallback


def members(uid, conversation_id, *, episode_id=None):
    episode = (
        episodes_db.get_episode(uid, episode_id)
        if episode_id
        else episodes_db.get_episode_for_conversation(uid, conversation_id)
    )
    if episode_id and not episode:
        raise LookupError('Episode not found')
    anchor = conversations_db.get_conversation(uid, conversation_id)
    if not anchor or anchor.get('deleted'):
        raise LookupError('Conversation not found')
    if anchor.get('is_locked'):
        raise PermissionError('Conversation is locked')
    scopes = {s.get('speaker_id_scope') for s in anchor.get('transcript_segments') or []} - {None, ''}
    if episode:
        ids = episode.get('conversation_ids') or []
        if conversation_id not in ids:
            raise ValueError('Conversation is no longer in this recording')
        rows = [anchor if cid == conversation_id else conversations_db.get_conversation(uid, cid) for cid in ids]
    elif scopes:
        collection = get_firestore_client().collection('users').document(uid).collection('conversations')
        rows = []
        for snapshot in collection.stream():
            raw = snapshot.to_dict() or {}
            if raw.get('deleted'):
                continue
            segments = conversations_db.decode_transcript_segments_verified(
                uid, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
            )
            if any(s.get('speaker_id_scope') in scopes for s in segments):
                rows.append(conversations_db.get_conversation(uid, snapshot.id))
    else:
        rows = [anchor]
    return episode, [row for row in rows if row and not row.get('deleted')]


def transcript(uid, conversation_id):
    episode, rows = members(uid, conversation_id)
    if any(row.get('is_locked') for row in rows):
        raise PermissionError('Conversation is locked')
    # Only fields needed by the picker. Avoid exposing server receipt/evidence internals.
    return {
        'episode_id': episode['id'] if episode else None,
        'conversations': [
            {
                'id': row['id'],
                'transcript_segments': [
                    dict(
                        TranscriptSegment(**dict(s, is_user=s.get('is_user', False))).model_dump(mode='json'),
                        stream_speaker=canonical_speaker_label(str(s.get('speaker') or '')),
                    )
                    for s in row.get('transcript_segments') or []
                ],
            }
            for row in rows
        ],
    }


def assign(uid, conversation_id, body: RecordingSpeakerRequest, background_tasks, *, episode_id=None):
    episode, rows = members(uid, conversation_id, episode_id=episode_id)
    by_id = {row['id']: row for row in rows}
    targets = {}
    voice_cache, segment_voice_cache, expanded = {}, {}, set()

    def known_voices(row, scope):
        key = row['id'], scope
        if key not in voice_cache:
            voice_cache[key] = voice_segments(row, scope)
            segment_voice_cache[key] = {s['id']: label for label, lines in voice_cache[key].items() for s in lines}
        return voice_cache[key]

    if body.voice:
        scope = body.voice.speaker_id_scope
        label = canonical_speaker_label(body.voice.stream_speaker)
        for row in rows:
            for line in known_voices(row, scope).get(label, []):
                targets.setdefault(row['id'], {})[line['id']] = (scope, label)
        if not targets:
            raise ValueError('Selected speaker changed; select the lines again')
    # Validate every selected row before any write. Each commit rechecks the exact
    # voice and segment ids inside its own existing receipt transaction.
    for selection in body.selections:
        row = by_id.get(selection.conversation_id)
        if row is None:
            raise ValueError('Selected lines are no longer in this recording')
        manual_assignment(
            row,
            person_id=body.person_id,
            is_user=body.is_user,
            segment_ids=selection.segment_ids,
            speaker_id=selection.speaker_id,
        )
        selected = [s for s in row.get('transcript_segments') or [] if s.get('id') in selection.segment_ids]
        for segment in selected:
            scope = segment.get('speaker_id_scope')
            known_voices(row, scope)
            voice = segment_voice_cache[(row['id'], scope)].get(segment['id'])
            if body.whole_recording and voice:
                if (scope, voice) in expanded:
                    continue
                expanded.add((scope, voice))
                for member in rows:
                    matching = known_voices(member, scope).get(voice, [])
                    for line in matching:
                        targets.setdefault(member['id'], {})[line['id']] = (scope, voice)
            elif body.whole_recording and not scope:
                legacy = row['id'], segment.get('speaker_id')
                if legacy in expanded:
                    continue
                expanded.add(legacy)
                for line in row.get('transcript_segments') or []:
                    if not line.get('speaker_id_scope') and line.get('speaker_id') == segment.get('speaker_id'):
                        targets.setdefault(row['id'], {})[line['id']] = (None, line.get('speaker_id'))
            else:
                targets.setdefault(row['id'], {})[segment['id']] = (
                    (scope, voice) if voice else (None, segment.get('speaker_id'))
                )
    if any(by_id[cid].get('is_locked') for cid in targets):
        raise PermissionError('Conversation is locked')
    if body.whole_recording and any(voice[0] is None for ids in targets.values() for voice in ids.values()):
        record_fallback(component='other', from_mode='other', to_mode='incumbent', reason='other', outcome='degraded')
    applied = []
    decided_at = datetime.now(timezone.utc).isoformat()
    for cid, ids in targets.items():
        raw, resolved, _, _ = commit_manual_assignment(
            uid,
            cid,
            person_id=body.person_id,
            is_user=body.is_user,
            segment_ids=list(ids),
            use_for_speech_training=body.use_for_speech_training,
            background_tasks=background_tasks,
            expected_voices=ids,
            decided_at=decided_at,
            recording_voice_defaults=body.whole_recording or body.voice is not None,
        )
        applied.append({'conversation_id': raw['id'], 'applied_count': len(resolved)})
    return {
        'episode_id': episode['id'] if episode else None,
        'conversations': applied,
        'applied_count': sum(row['applied_count'] for row in applied),
    }


def recording_carry(uid, previous, active_scope):
    """Use the latest scoped decisions even when the last member has no such voice."""
    from database import recording_speakers as decisions_db

    try:
        decisions = decisions_db.read(uid, active_scope)
        if not isinstance(decisions, dict) or any(not isinstance(entry, dict) for entry in decisions.values()):
            raise ValueError('Malformed recording decisions')
    except Exception:
        record_fallback(component='other', from_mode='other', to_mode='incumbent', reason='other', outcome='degraded')
        return carried_receipt(previous, active_scope)
    for entry in (carried_receipt(previous, active_scope).get('speakers') or {}).values():
        label = entry['stream_speaker']
        if label not in decisions or entry.get('decided_at', '') > decisions[label].get('decided_at', ''):
            decisions[label] = entry
    speakers = {str(entry['speaker_id']): entry for entry in decisions.values()}
    if len(speakers) != len(decisions):
        record_fallback(component='other', from_mode='other', to_mode='incumbent', reason='other', outcome='degraded')
        return carried_receipt(previous, active_scope)
    return {'generation': 1, 'speakers': speakers} if speakers else {}
