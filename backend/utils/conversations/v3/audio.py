"""Owner-checked recording audio aliases and window manifests."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from database import conversations as conversations_db
from utils.conversations.v3.outline import utc


def resolve(uid, conversation, audio_file):
    rid = audio_file.get('recording_id')
    if not rid:
        return conversation['id'], audio_file, conversation
    # Both lookups are scoped to the authenticated owner, never a supplied UID.
    recording = conversations_db.get_conversation(uid, rid)
    if (
        not recording
        or not recording.get('recording')
        or recording.get('deleted')
        or recording.get('is_locked')
        or not any(c['conversation_id'] == conversation['id'] for c in recording.get('claims') or [])
    ):
        raise HTTPException(404, 'Audio file not found in conversation')
    source_id = audio_file.get('recording_file_id') or audio_file['id']
    original = next((af for af in recording.get('audio_files') or [] if af['id'] == source_id), None)
    if original is None:
        raise HTTPException(404, 'Audio file not found in recording')
    return rid, original, recording


def subtract_spans(start, end, deleted):
    intervals = [(start, end)]
    for left, right in deleted:
        next_intervals = []
        for a, b in intervals:
            if b <= left or a >= right:
                next_intervals.append((a, b))
            else:
                if a < left:
                    next_intervals.append((a, left))
                if b > right:
                    next_intervals.append((right, b))
        intervals = next_intervals
    return intervals


def manifest(uid, conversation):
    from utils.sync.playback import get_audio_signed_urls

    result = []
    now = datetime.now(timezone.utc)
    files = conversation.get('audio_files') or []
    pieces = conversation.get('recording_pieces')
    if pieces is None:
        pieces = [
            {'recording_id': conversation['id'], 'audio_file_id': af['id'], 'start': 0.0, 'end': af.get('duration', 0)}
            for af in files
        ]
    for piece in pieces:
        alias = next(
            (
                af
                for af in files
                if (af.get('recording_file_id') or af['id']) == piece['audio_file_id']
                and (af.get('recording_id') or conversation['id']) == piece['recording_id']
            ),
            None,
        )
        if not alias:
            raise HTTPException(503, 'Audio metadata is being prepared')
        rid, original, recording = resolve(uid, conversation, alias)
        response = get_audio_signed_urls(uid, rid, [original], conversation=recording)
        url_info = next((af for af in response.get('audio_files', []) if af['id'] == original['id']), {})
        url = url_info.get('signed_url')
        if not url:
            raise HTTPException(503, 'Audio is being prepared', headers={'Retry-After': '3'})
        stamps = original.get('chunk_timestamps') or []
        origin = utc(original.get('started_at')) or (
            datetime.fromtimestamp(min(stamps), timezone.utc) if stamps else utc(recording.get('started_at'))
        )
        deleted = [
            ((utc(s['start']) - origin).total_seconds(), (utc(s['end']) - origin).total_seconds())
            for s in recording.get('deleted_spans') or []
        ]
        for a, b in subtract_spans(piece['start'], piece['end'], deleted):
            result.append(
                {
                    **piece,
                    'start': a,
                    'end': b,
                    'url': url,
                    'expires_at': url_info.get('expires_at') or now + timedelta(minutes=5),
                }
            )
    return {'pieces': result}
