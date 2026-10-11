"""Carry explicit manual speaker decisions across a same-stream conversation rollover.

A recording rotation mints a new conversation row while the provider stream —
and therefore its (scope, speaker label) voice identity — continues. This pure
helper projects the previous conversation's *winning* manual receipt decisions
onto the new row: only voices the caller actually labeled on the still-active
provider scope carry, never an automatic match or a mapped suggestion.
"""

from typing import Any, Dict, List, Mapping, Optional

from utils.manual_speaker_assignments import manual_rejected_speakers
from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL, canonical_speaker_label

_IDENTITY_KEYS = ('person_id', 'is_user', 'use_for_speech_training', 'rejection')


def _identity(decision: Mapping[str, Any]) -> tuple:
    return (
        bool(decision.get('is_user')),
        decision.get('person_id'),
        bool(decision.get('use_for_speech_training', True)),
        (decision.get('rejection') or {}).get('kind'),
        (decision.get('rejection') or {}).get('person_id'),
    )


def _active_entries(entries: Optional[Mapping[str, Any]], active_scope: str) -> Dict[str, Mapping[str, Any]]:
    return {
        key: entry
        for key, entry in (entries or {}).items()
        if isinstance(entry, Mapping)
        and not (entry.get('source') == 'carried' and entry.get('speaker_id_scope') != active_scope)
    }


def _winning(
    receipt: Mapping[str, Any], rejected: Mapping[int, Any], segment: Mapping[str, Any]
) -> Optional[Mapping[str, Any]]:
    candidates = [
        decision
        for decision in (
            (receipt.get('segments') or {}).get(segment.get('id')),
            (receipt.get('speakers') or {}).get(str(segment.get('speaker_id'))),
        )
        if isinstance(decision, Mapping)
    ]
    speaker_id = segment.get('speaker_id')
    negative = rejected.get(speaker_id) if isinstance(speaker_id, int) else None
    if negative is not None:
        scope = negative.get('speaker_id_scope')
        if scope is None or scope == segment.get('speaker_id_scope'):
            candidates.append(negative)
    if not candidates:
        return None
    return max(candidates, key=lambda decision: decision.get('generation', 0))


def carried_receipt(conversation: Mapping[str, Any], active_scope: Optional[str]) -> Dict[str, Any]:
    """speaker_id -> carried decision for every labeled voice on ``active_scope``.

    Voices are collected by (scope, canonical provider label), never by the
    conversation-local integer alone. A voice carries only when the latest
    winning decision across its segments is one unambiguous explicit decision;
    conflicting same-generation identities skip the voice. The result is a
    generation-1 receipt whose speaker entries keep the allocated speaker id,
    mark ``source='carried'``, and name the stream-local provider label.
    """
    if not active_scope:
        return {}
    raw = conversation.get('manual_speaker_assignments') or {}
    if not isinstance(raw, Mapping):
        return {}
    receipt = {
        **raw,
        'segments': _active_entries(raw.get('segments'), active_scope),
        'speakers': _active_entries(raw.get('speakers'), active_scope),
    }
    rejected = manual_rejected_speakers(receipt)
    voices: Dict[tuple, List[Mapping[str, Any]]] = {}
    for segment in conversation.get('transcript_segments') or []:
        if not isinstance(segment, Mapping):
            continue
        speaker_id = segment.get('speaker_id')
        label = segment.get('speaker')
        if (
            segment.get('speaker_id_scope') != active_scope
            or not isinstance(speaker_id, int)
            or speaker_id == OMI_SPEAKER_ID_SENTINEL
            or not label
            or segment.get('audio_alignment') == 'unplaced'
        ):
            continue
        voices.setdefault((active_scope, canonical_speaker_label(str(label))), []).append(segment)

    speakers: Dict[str, Dict[str, Any]] = {}
    for (_scope, label), segments in voices.items():
        speaker_ids = {segment['speaker_id'] for segment in segments}
        if len(speaker_ids) != 1:
            continue
        decisions = [d for d in (_winning(receipt, rejected, s) for s in segments) if d is not None]
        if not decisions:
            continue
        top = max(decision.get('generation', 0) for decision in decisions)
        winners = [decision for decision in decisions if decision.get('generation', 0) == top]
        if len({_identity(decision) for decision in winners}) != 1:
            continue
        decision = winners[0]
        if decision.get('segment_only'):
            continue
        entry: Dict[str, Any] = {
            'generation': 1,
            'source': 'carried',
            'speaker_id': speaker_ids.pop(),
            'speaker_id_scope': active_scope,
            'stream_speaker': label,
            'carried_from_conversation_id': conversation.get('id'),
        }
        for key in _IDENTITY_KEYS:
            if key in decision:
                entry[key] = decision[key]
        speakers[str(entry['speaker_id'])] = entry
    if not speakers:
        return {}
    return {'generation': 1, 'speakers': speakers}
