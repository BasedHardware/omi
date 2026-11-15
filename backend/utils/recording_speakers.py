"""Explicit naming across a recording; never joins embeddings or different scopes.

Episode membership and indexed scopes are augmented by bounded legacy
origin/session queries. Completeness requires creation-time index provenance;
later index repairs cannot certify a legacy lineage. No migration is needed.
"""

from datetime import datetime, timezone

from config.recording_speakers import MAX_SCOPES, MAX_MEMBERS, SCOPE_INDEX_AT_CREATION_FIELD, check_budget, enabled

from database import conversations as conversations_db, episodes as episodes_db
from database.recording_speakers import scope_conversation_ids, legacy_recording_conversation_ids
from models.transcript_segment import TranscriptSegment
from models.recording_speakers import RecordingSpeakerRequest
from utils.stt.speaker_identity import canonical_speaker_label
from utils.live_speaker_carry import carried_receipt, voice_segments
from utils.manual_speaker_assignments import assignment_segments, manual_assignment
from utils.speaker_assignment_teaching import commit_manual_assignment
from utils.observability.fallback import record_fallback
from utils.conversations.fragment_visibility import is_relevance_discarded


def _current_conversation(uid, conversation_id):
    seen = set()
    while conversation_id not in seen and len(seen) < 16:
        seen.add(conversation_id)
        row = conversations_db.get_conversation(uid, conversation_id)
        if not row:
            break
        if not row.get('deleted'):
            if is_relevance_discarded(row):
                raise LookupError('Conversation not found')
            return dict(row, id=conversation_id)
        conversation_id = row.get('sync_merged_into')
        if not conversation_id:
            break
    raise LookupError('Conversation not found')


def members(uid, conversation_id, *, episode_id=None, extra_scopes=()):
    anchor = _current_conversation(uid, conversation_id)
    conversation_id = anchor['id']
    if not enabled():
        return None, [dict(anchor, transcript_segments=assignment_segments(anchor))], 'partial'
    episode = (
        episodes_db.get_episode(uid, episode_id)
        if episode_id
        else episodes_db.get_episode_for_conversation(uid, conversation_id)
    )
    if episode_id and not episode:
        raise LookupError('Episode not found')
    if anchor.get('is_locked'):
        raise PermissionError('Conversation is locked')
    scopes = ({s.get('speaker_id_scope') for s in anchor.get('transcript_segments') or []} | set(extra_scopes)) - {
        None,
        '',
    }
    coverage = 'complete' if episode else 'partial'
    excluded_ids = set()
    if episode:
        excluded_ids = set(episode.get('discarded_conversation_ids') or []) | set(
            episode.get('duplicate_conversation_ids') or []
        )
        ids = list(dict.fromkeys([*(episode.get('conversation_ids') or []), *sorted(excluded_ids)]))
        check_budget(len(ids))
        if conversation_id not in ids:
            raise ValueError('Conversation is no longer in this recording')
        rows = [
            dict(row, id=cid)
            for cid in ids
            if (row := (anchor if cid == conversation_id else conversations_db.get_conversation(uid, cid)))
        ]
    elif scopes:
        indexed = set(scope_conversation_ids(uid, scopes))
        external = anchor.get('external_data') or {}
        origin = external.get('recording_origin_id') or external.get('recording_session_id')
        legacy = legacy_recording_conversation_ids(uid, origin) if origin else []
        ids = list(dict.fromkeys([conversation_id, *sorted(indexed), *legacy]))
        check_budget(len(ids))
        # Indexed membership is necessary but insufficient: old renames may
        # have indexed only c0/c2 while leaving an invisible c1 behind.
        coverage = 'complete' if set(ids) <= indexed else 'partial'
        rows = [dict(row, id=cid) for cid in ids if (row := conversations_db.get_conversation(uid, cid))]
    else:
        ids, rows = [conversation_id], [anchor]
    check_budget(len(ids), sum(len(row.get('transcript_segments') or []) for row in rows))
    rows = [
        row
        for row in rows
        if row
        and row['id'] not in excluded_ids
        and not row.get('deleted')
        and not row.get('is_locked')
        and not is_relevance_discarded(row)
    ]
    if len(rows) != len(ids) or any(row.get(SCOPE_INDEX_AT_CREATION_FIELD) is not True for row in rows):
        coverage = 'partial'
    if coverage == 'partial':
        record_fallback(component='other', from_mode='other', to_mode='incumbent', reason='other', outcome='degraded')
    return episode, [dict(row, transcript_segments=assignment_segments(row)) for row in rows], coverage


def _recorded_start(row):
    value = row.get('started_at') or row.get('created_at')
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.timestamp() if isinstance(value, datetime) else None


def transcript(uid, conversation_id):
    episode, rows, coverage = members(uid, conversation_id)
    if any(row.get('is_locked') for row in rows):
        raise PermissionError('Conversation is locked')
    rows.sort(key=lambda row: (_recorded_start(row) or 0, row['id']))
    starts = [value for row in rows if (value := _recorded_start(row)) is not None]
    origin = min(starts) if starts else 0
    # Only fields needed by the picker. Avoid exposing server receipt/evidence internals.
    return {
        'enabled': enabled(),
        'episode_id': episode['id'] if episode else None,
        'coverage': coverage,
        'conversations': [
            {
                'id': row['id'],
                'recording_offset_seconds': max(0, (_recorded_start(row) or origin) - origin),
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
    check_budget(len({s.conversation_id for s in body.selections}), sum(len(s.segment_ids) for s in body.selections))
    episode, rows, coverage = members(uid, conversation_id, episode_id=episode_id)
    by_id = {row['id']: row for row in rows}
    selections = [
        (
            selection
            if selection.conversation_id in by_id
            else selection.model_copy(
                update={'conversation_id': _current_conversation(uid, selection.conversation_id)['id']}
            )
        )
        for selection in body.selections
    ]
    selected_ids_by_conversation = {}
    for selection in selections:
        selected_ids_by_conversation.setdefault(selection.conversation_id, set()).update(selection.segment_ids)
    selected_scopes = (
        {body.voice.speaker_id_scope}
        if body.voice
        else {
            s.get('speaker_id_scope')
            for cid, selected_ids in selected_ids_by_conversation.items()
            for s in (by_id.get(cid) or {}).get('transcript_segments') or []
            if s.get('id') in selected_ids and s.get('speaker_id_scope')
        }
    )
    if len(selected_scopes) > MAX_SCOPES:
        check_budget(MAX_MEMBERS + 1)
    if episode is None:
        # A selected sibling may contain a later scope absent in the open row.
        # Only that selected scope may expand discovery, never a speaker number.
        anchor_scopes = {
            s.get('speaker_id_scope')
            for s in (by_id.get(conversation_id) or _current_conversation(uid, conversation_id)).get(
                'transcript_segments'
            )
            or []
        }
        if selected_scopes - anchor_scopes:
            _, rows, coverage = members(uid, conversation_id, extra_scopes=selected_scopes)
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
    for selection in selections:
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
        selected_ids = set(selection.segment_ids)
        selected = [s for s in row.get('transcript_segments') or [] if s.get('id') in selected_ids]
        if (
            selection.speaker_id is not None
            and body.whole_recording
            and not selection.voice
            and any(s.get('speaker_id_scope') for s in selected)
        ):
            raise ValueError('Scoped speaker rename requires the selected voice identity')
        for segment in selected:
            if selection.voice and (
                segment.get('speaker_id_scope') != selection.voice.speaker_id_scope
                or canonical_speaker_label(str(segment.get('speaker') or ''))
                != canonical_speaker_label(selection.voice.stream_speaker)
            ):
                raise ValueError('Selected speaker changed; select the lines again')
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
                    (scope, voice or canonical_speaker_label(str(segment.get('speaker') or '')))
                    if scope
                    else (None, segment.get('speaker_id'))
                )
    if any(by_id[cid].get('is_locked') for cid in targets):
        raise PermissionError('Conversation is locked')
    if body.whole_recording and any(voice[0] is None for ids in targets.values() for voice in ids.values()):
        record_fallback(component='other', from_mode='other', to_mode='incumbent', reason='other', outcome='degraded')
    applied = []
    decided_at = datetime.now(timezone.utc).isoformat()
    check_budget(len(targets), sum(len(ids) for ids in targets.values()))
    if len({voice[0] for ids in targets.values() for voice in ids.values() if voice[0]}) > MAX_SCOPES:
        check_budget(MAX_MEMBERS + 1)
    for cid, ids in targets.items():
        try:
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
        except (ValueError, LookupError, PermissionError):
            applied.append({'conversation_id': cid, 'applied_count': 0, 'error': 'stale_speaker'})
        except Exception:
            # Earlier members may already be committed. Report every outcome so
            # clients never roll those labels back after a later member fails.
            record_fallback(component='other', from_mode='other', to_mode='none', reason='other', outcome='degraded')
            applied.append({'conversation_id': cid, 'applied_count': 0, 'error': 'save_failed'})
    if {row['conversation_id'] for row in applied if not row.get('error')} != set(by_id):
        coverage = 'partial'
    return {
        'episode_id': episode['id'] if episode else None,
        'coverage': coverage,
        'conversations': applied,
        'applied_count': sum(row['applied_count'] for row in applied),
    }


def recording_carry(uid, previous, active_scope):
    """Use the latest scoped decisions even when the last member has no such voice."""
    from database import recording_speakers as decisions_db

    if not enabled():
        return carried_receipt(previous, active_scope)
    if not active_scope:
        return {}
    try:
        decisions = decisions_db.read(uid, active_scope)
        if not isinstance(decisions, dict) or any(
            not isinstance(entry, dict)
            or not isinstance(entry.get('speaker_id'), int)
            or entry.get('speaker_id_scope') != active_scope
            or not isinstance(entry.get('stream_speaker'), str)
            or not entry.get('stream_speaker')
            or not isinstance(entry.get('decided_at', ''), str)
            for entry in decisions.values()
        ):
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
