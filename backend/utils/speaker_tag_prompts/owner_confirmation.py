"""Pure, server-bound evidence for one excerpt-only owner question.

Stored diagnostic distances are not pooled distances. The serving boundary must
supply embeddings of these complete windows; identities never rank a question.
"""

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from models.speaker_tag_prompts import SpeakerTagPrompt, SpeakerTagPromptOrigin
from models.transcript_segment import legacy_conversation_segment_id
from utils.speaker_tag_prompts.coverage import prompt_window_covered
from utils.speaker_learning_policy import union_seconds

FIELD = 'owner_confirmation_prompt'
MIN_SECONDS = 5.0
MAX_SECONDS = 10.0
MAX_CONSTITUENTS = 16


class StaleOwnerConfirmation(ValueError):
    """The played evidence no longer authorizes an answer."""


def label_identity(segment: Mapping[str, Any]) -> str:
    if segment.get('speaker_identity_status') == 'ambiguous':
        return 'none'
    if segment.get('is_user'):
        return 'user'
    if segment.get('person_id'):
        return f"person:{segment['person_id']}"
    return 'none'


def baseline_origin(segments: Sequence[Mapping[str, Any]]) -> str:
    identities = {label_identity(segment) for segment in segments}
    if len(identities) != 1:
        return 'mixed'
    identity = next(iter(identities))
    if identity == 'user':
        return SpeakerTagPromptOrigin.auto_user.value
    if identity.startswith('person:'):
        return SpeakerTagPromptOrigin.auto_person.value
    return SpeakerTagPromptOrigin.unnamed.value


def normalized_segments(conversation: Mapping[str, Any]) -> list[dict]:
    result = []
    for i, raw in enumerate(conversation.get('transcript_segments') or []):
        s = dict(raw, id=raw.get('id') or legacy_conversation_segment_id(conversation['id'], i))
        if s.get('speaker_id') is None:
            try:
                s['speaker_id'] = int(str(s.get('speaker') or 'SPEAKER_00').split('_', 1)[1])
            except (ValueError, IndexError):
                s['speaker_id'] = 0
        result.append(s)
    return result


def fingerprint(conversation: Mapping[str, Any]) -> str:
    # Deliberately bind the whole roster: regrouping, overlapping additions and
    # label edits invalidate a card, even if its selected IDs happened to survive.
    payload = [
        conversation.get('id'),
        conversation.get('started_at'),
        conversation.get('status'),
        conversation.get('audio_files'),
        conversation.get('audio_timeline'),
        conversation.get('conversation_audio'),
        [
            {
                key: s.get(key)
                for key in (
                    'id',
                    'speaker_id',
                    'speaker_id_scope',
                    'text',
                    'start',
                    'end',
                    'is_user',
                    'person_id',
                    'speaker_identity_status',
                    'audio_alignment',
                    'audio_capture_run',
                    'audio_capture_start',
                    'audio_capture_end',
                    'audio_source',
                )
            }
            for s in normalized_segments(conversation)
        ],
        conversation.get('manual_speaker_assignments') or {},
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def source_key(segment: Mapping[str, Any]) -> str:
    source = segment.get('audio_source')
    if isinstance(source, Mapping) and source.get('type') == 'sync':
        # Sync source bounds vary by segment, but a contiguous excerpt must
        # share the same authoritative clock offset.
        try:
            start_delta = float(source['start']) - float(segment['start'])
            end_delta = float(source['end']) - float(segment['end'])
            if not math.isfinite(start_delta) or abs(start_delta - end_delta) > 0.001:
                return json.dumps(source, sort_keys=True)
            return f'sync:{round(start_delta, 3)}'
        except (KeyError, TypeError, ValueError):
            return json.dumps(source, sort_keys=True, default=str)
    return json.dumps(source, sort_keys=True, default=str)


def voice_key(segment: Mapping[str, Any]) -> tuple:
    return (
        segment.get('speaker_id_scope'),
        segment.get('speaker_id'),
        segment.get('audio_capture_run'),
        source_key(segment),
    )


def validate_window(conversation: Mapping[str, Any], ids: Sequence[str], start: float, end: float) -> list[dict]:
    if (
        not ids
        or len(ids) > 50
        or len(set(ids)) != len(ids)
        or not math.isfinite(start)
        or not math.isfinite(end)
        or start < 0
        or not MIN_SECONDS <= end - start <= MAX_SECONDS
    ):
        raise StaleOwnerConfirmation('Invalid owner excerpt')
    all_segments = normalized_segments(conversation)
    selected = [s for s in all_segments if s['id'] in ids]
    if len(selected) != len(ids) or len({voice_key(s) for s in selected}) != 1:
        raise StaleOwnerConfirmation('Owner excerpt changed')
    for s in selected:
        a, b = s.get('start'), s.get('end')
        if (
            s.get('audio_alignment') == 'unplaced'
            or isinstance(a, bool)
            or isinstance(b, bool)
            or not isinstance(a, (float, int))
            or not isinstance(b, (float, int))
            or not math.isfinite(a)
            or not math.isfinite(b)
            or not start <= a < b <= end
        ):
            raise StaleOwnerConfirmation('Owner excerpt must contain complete placed segments')
    if union_seconds([(s['start'], s['end']) for s in selected]) < MIN_SECONDS:
        raise StaleOwnerConfirmation('Insufficient speech in owner excerpt')
    if min(s['start'] for s in selected) != start or max(s['end'] for s in selected) != end:
        raise StaleOwnerConfirmation('Owner excerpt bounds changed')
    # Any unselected audio overlapping the cut could put an unplayed decision or
    # a different capture/speaker into it. Never authorize that union.
    if any(
        s['id'] not in ids
        and isinstance(s.get('start'), (int, float))
        and isinstance(s.get('end'), (int, float))
        and s['start'] < end
        and s['end'] > start
        for s in all_segments
    ):
        raise StaleOwnerConfirmation('Owner excerpt overlaps other evidence')
    if not prompt_window_covered(conversation, start, end):
        raise StaleOwnerConfirmation('Owner excerpt audio changed')
    return selected


def binding_for(conversation: Mapping[str, Any], prompt: SpeakerTagPrompt) -> dict:
    selected = validate_window(conversation, prompt.segment_ids, prompt.clip_start, prompt.clip_end)
    if selected[0]['speaker_id'] != prompt.speaker_id:
        raise StaleOwnerConfirmation('Owner excerpt speaker changed')
    digest = fingerprint(conversation)
    binding = dict(
        prompt_id=prompt.id,
        segment_ids=prompt.segment_ids,
        clip_start=prompt.clip_start,
        clip_end=prompt.clip_end,
        speaker_id=prompt.speaker_id,
        speaker_id_scope=selected[0].get('speaker_id_scope'),
        audio_capture_run=selected[0].get('audio_capture_run'),
        receipt_generation=(conversation.get('manual_speaker_assignments') or {}).get('generation', 0),
        fingerprint=digest,
        origin=baseline_origin(selected),
        baseline_labels=[
            {key: segment.get(key) for key in ('id', 'is_user', 'person_id', 'speaker_identity_status')}
            for segment in sorted(selected, key=lambda segment: segment['id'])
        ],
    )
    binding['evidence_id'] = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    return binding


def validate_binding(
    conversation: Mapping[str, Any],
    prompt_id: str,
    evidence_id: str,
    segment_ids: Sequence[str] | None = None,
    *,
    require_played: bool = False,
) -> dict:
    binding = conversation.get(FIELD) or {}
    if (
        conversation.get('deleted')
        or conversation.get('discarded')
        or conversation.get('is_locked')
        or conversation.get('status') != 'completed'
        or binding.get('answered')
        or binding.get('prompt_id') != prompt_id
        or binding.get('evidence_id') != evidence_id
        or binding.get('fingerprint') != fingerprint(conversation)
        or (segment_ids is not None and list(segment_ids) != binding.get('segment_ids'))
        or (require_played and not binding.get('played_pcm_sha256'))
    ):
        raise StaleOwnerConfirmation('Owner question is stale; refresh the conversation')
    validate_window(conversation, binding['segment_ids'], binding['clip_start'], binding['clip_end'])
    return binding
