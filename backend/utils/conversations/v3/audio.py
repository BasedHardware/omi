"""Owner-checked recording audio aliases and window-exact conversation playback artifacts."""

import hashlib
import io
import json
from typing import Any

from fastapi import HTTPException

from database import conversations as conversations_db
from utils.conversations.v3.outline import utc, playback_origin


class V3PieceNotReady(RuntimeError):
    def __init__(self):
        super().__init__('v3_piece_not_ready')


def playback_piece_scope(conversation: dict[str, Any]) -> str:
    """Identify the requested windows independently of late source metadata."""
    return hashlib.sha256(
        json.dumps(
            [conversation.get('started_at'), conversation['recording_pieces']], sort_keys=True, default=str
        ).encode()
    ).hexdigest()


def resolve(uid, conversation, audio_file):
    owner = conversations_db.get_conversation(uid, conversation['id'])
    if not owner or owner.get('deleted') or owner.get('is_locked'):
        raise HTTPException(404, 'Conversation not found')
    return _resolve(uid, owner, audio_file)


def _resolve(uid, conversation, audio_file):
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


def playback_snapshot(uid, conversation) -> dict[str, Any]:
    """Resolve current owner-scoped pieces, including deletion/source revisions.

    Missing pieces do not authorize playing their covering file. They contribute
    an absent marker to the fingerprint, so their arrival self-heals the cache.
    """
    owner = conversations_db.get_conversation(uid, conversation['id'])
    if not owner or owner.get('deleted') or owner.get('is_locked'):
        raise HTTPException(404, 'Conversation not found')
    parts = []
    for piece in owner.get('recording_pieces') or []:
        alias = next(
            (
                af
                for af in owner.get('audio_files') or []
                # Audio a merge copied from a legacy conversation has no recording alias: it belongs to
                # this conversation under its own file id.
                if (af.get('recording_id') or owner['id']) == piece['recording_id']
                and (af.get('recording_file_id') or af['id']) == piece['audio_file_id']
            ),
            None,
        )
        part = {'piece': piece}
        try:
            if alias is None:
                raise HTTPException(404)
            rid, original, recording = _resolve(uid, owner, alias)
            stamps = original.get('chunk_timestamps') or []
            origin = playback_origin(original, recording)
            if origin is not None and stamps:
                deleted = [
                    ((utc(s['start']) - origin).total_seconds(), (utc(s['end']) - origin).total_seconds())
                    for s in recording.get('deleted_spans') or []
                ]
                part.update(
                    recording_id=rid,
                    source=original,
                    origin=origin,
                    intervals=subtract_spans(piece['start'], piece['end'], deleted),
                )
            else:
                part['pending'] = True
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
        parts.append(part)
    fingerprint = hashlib.sha256(
        json.dumps(
            {'format': 'v3-window-pcm-v2', 'origin': owner.get('started_at'), 'parts': parts},
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    return {**owner, '_v3_playback_parts': parts, '_v3_playback_fingerprint': fingerprint}


def build_artifact(uid, conversation):
    from utils.sync import playback

    pcm_buf = bytearray()
    spans = []
    origin = utc(conversation['started_at'])
    parts = sorted(
        conversation['_v3_playback_parts'],
        key=lambda p: (str(p.get('origin') or ''), p['piece']['start'], p['piece']['recording_id']),
    )
    for part in parts:
        if part.get('pending'):
            raise V3PieceNotReady()
        if 'source' not in part or not part.get('intervals'):
            continue
        af = part['source']
        try:
            selected = None
            if af.get('source_fingerprint'):
                selected = playback.resolve_sources(
                    af, playback.list_audio_chunks(uid, part['recording_id'], source_identity=True)
                )
            pcm = playback._merge_playback_sources(  # pyright: ignore[reportPrivateUsage] -- shared source identity/PCM assembly
                uid, part['recording_id'], sorted(af['chunk_timestamps']), selected
            )
            if selected is not None:
                playback.validate_sources(
                    [af], playback.list_audio_chunks(uid, part['recording_id'], source_identity=True)
                )
        except FileNotFoundError as exc:
            raise V3PieceNotReady() from exc
        for left, right in part['intervals']:
            # Align slices to PCM16 sample boundaries, never encoder padding.
            a, b = int(left * playback.AUDIO_SAMPLE_RATE) * 2, int(right * playback.AUDIO_SAMPLE_RATE) * 2
            if b > len(pcm):
                raise V3PieceNotReady()
            clipped = pcm[a:b]
            if not clipped:
                continue
            spans.append(
                {
                    'file_id': af['id'],
                    'wall_offset': round((part['origin'] - origin).total_seconds() + left, 3),
                    'artifact_offset': round(len(pcm_buf) / (playback.AUDIO_SAMPLE_RATE * 2), 3),
                    'len': round(len(clipped) / (playback.AUDIO_SAMPLE_RATE * 2), 3),
                }
            )
            pcm_buf.extend(clipped)
    if not pcm_buf:
        raise FileNotFoundError('No playable conversation pieces')
    segment = playback.AudioSegment(
        data=bytes(pcm_buf), sample_width=2, frame_rate=playback.AUDIO_SAMPLE_RATE, channels=1
    )
    buf = io.BytesIO()
    segment.export(buf, format='mp3', bitrate='48k')
    return buf.getvalue(), spans


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
