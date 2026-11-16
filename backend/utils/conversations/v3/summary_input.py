"""Content identity for speculative notes, independent of transport seals and wall time."""

import hashlib
import json
from datetime import datetime
from enum import Enum

from utils.conversations.v3 import policy
from models.transcript_segment import TranscriptSegment, legacy_conversation_segment_id


def _json(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json', exclude_none=True)
    raise TypeError(type(value).__name__)


def _voice(segment):
    # Notes receive this model's legacy numeric defaults before display groups voices.
    normalized = TranscriptSegment(
        id='summary-input',
        text='',
        speaker=policy.field(segment, 'speaker') or 'SPEAKER_00',
        speaker_id=policy.field(segment, 'speaker_id'),
        speaker_id_scope=policy.field(segment, 'speaker_id_scope'),
        is_user=False,
        start=0,
        end=0,
    )
    return {'speaker_id': normalized.speaker_id, 'speaker_id_scope': normalized.speaker_id_scope}


def fingerprint(row):
    # Status, transport files, coverage and attempt metadata are not notes inputs.
    # Include bounds: the same text in a later outline split is a different snapshot.
    fields = (
        'started_at',
        'finished_at',
        'transcript_segments',
        'photos',
        'language',
        'source',
        'calendar_meeting_context',
        'external_data',
        'kind',
        'manual_end',
        'data_protection_level',
    )
    values = {key: policy.field(row, key) for key in fields}
    values['source'] = values['source'] or 'omi'
    values['kind'] = values['kind'] or 'conversation'
    values['manual_end'] = bool(values['manual_end'])
    values['photos'] = values['photos'] or []
    values['transcript_segments'] = [
        {
            'id': policy.field(s, 'id') or legacy_conversation_segment_id(str(policy.field(row, 'id')), index),
            'text': policy.field(s, 'text'),
            'original_text': policy.field(s, 'original_text'),
            'speaker': policy.field(s, 'speaker') or 'SPEAKER_00',
            **_voice(s),
            'is_user': bool(policy.field(s, 'is_user')),
            'person_id': policy.field(s, 'person_id'),
            'start': float(policy.field(s, 'start') or 0),
            'end': float(policy.field(s, 'end') or 0),
        }
        for index, s in enumerate(values['transcript_segments'] or [])
    ]
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=_json).encode()).hexdigest()


def eligible(row):
    return not policy.flag(row, 'v3_derived') or (
        policy.field(row, 'kind') not in {'media', 'background'}
        and (
            policy.manual_intent(row)
            or sum(len((policy.field(s, 'text') or '').split()) for s in policy.field(row, 'transcript_segments') or [])
            >= 300
        )
    )


def exact(row):
    covers, end = policy.field(row, 'summary_covers_through'), policy.field(row, 'finished_at')
    return bool(covers and end and covers == end and policy.field(row, 'summary_input_hash') == fingerprint(row))
