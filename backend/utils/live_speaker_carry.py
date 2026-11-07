"""Carry explicit manual speaker decisions across a same-stream conversation rollover.

A recording rotation mints a new conversation row while the provider stream —
and therefore its (scope, speaker label) voice identity — continues. This pure
helper projects the previous conversation's *winning* manual receipt decisions
onto the new row: only voices the caller actually labeled on the still-active
provider scope carry, never an automatic match or a mapped suggestion.
"""

from typing import Any, Dict, Mapping, Optional

from utils.manual_speaker_assignments import (
    _receipt_section,  # pyright: ignore[reportPrivateUsage]  # intentional shared receipt accessor
    manual_rejected_speakers,
    recording_voice_decision,
)
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
    if not isinstance(entries, Mapping):
        # A stored receipt section is user data: a wrong-typed value (a list, a
        # string) must not raise AttributeError on .items() here.
        return {}
    return {
        key: entry
        for key, entry in entries.items()
        if isinstance(entry, Mapping)
        and not (entry.get('source') == 'carried' and entry.get('speaker_id_scope') != active_scope)
    }


def _winning(
    receipt: Mapping[str, Any], rejected: Mapping[int, Any], segment: Mapping[str, Any]
) -> Optional[Mapping[str, Any]]:
    candidates = [
        decision
        for decision in (
            _receipt_section(receipt, 'segments').get(segment.get('id')),
            _receipt_section(receipt, 'speakers').get(str(segment.get('speaker_id'))),
            recording_voice_decision(segment, receipt),
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


def voice_segments(conversation: Mapping[str, Any], active_scope: Optional[str]) -> Dict[str, list]:
    """The same conservative voice collection used by rollover and recording edits."""
    voices: Dict[str, list] = {}
    if not active_scope:
        return voices
    for segment in conversation.get('transcript_segments') or []:
        if not isinstance(segment, Mapping):
            continue
        if (
            segment.get('speaker_id_scope') != active_scope
            or not isinstance(segment.get('speaker_id'), int)
            or segment['speaker_id'] == OMI_SPEAKER_ID_SENTINEL
            or not segment.get('speaker')
            or segment.get('audio_alignment') == 'unplaced'
        ):
            continue
        label = canonical_speaker_label(str(segment['speaker']))
        voices.setdefault(label, []).append(segment)
    return {label: rows for label, rows in voices.items() if len({s['speaker_id'] for s in rows}) == 1}


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
        # The sections are raw stored data, so a wrong-typed value is coerced to
        # {} before _active_entries iterates it — the crash site was one frame
        # earlier than the _winning() reads this receipt feeds.
        'segments': _active_entries(_receipt_section(raw, 'segments'), active_scope),
        'speakers': _active_entries(_receipt_section(raw, 'speakers'), active_scope),
    }
    rejected = manual_rejected_speakers(receipt)
    speakers: Dict[str, Dict[str, Any]] = {}
    for label, segments in voice_segments(conversation, active_scope).items():
        speaker_ids = {segment['speaker_id'] for segment in segments}
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
            'decided_at': decision.get('decided_at', ''),
        }
        for key in _IDENTITY_KEYS:
            if key in decision:
                entry[key] = decision[key]
        speakers[str(entry['speaker_id'])] = entry
    if not speakers:
        return {}
    return {'generation': 1, 'speakers': speakers}
