"""Reversible person voiceprint contributions. Pure; publication fences live in DB."""

from typing import Any, Mapping, Sequence

from utils.owner_voice_evidence import pool_owner_vectors
from utils.stt.voiceprints import usable_person_voiceprint

MAX_CONTRIBUTIONS = 5
POOL_KEY = 'person_voice_confirmations'
BASE_KEY = 'person_voice_base'


def _materialize(base: Mapping, entries: Sequence[Mapping]) -> dict[str, Any]:
    vectors = ([base['embedding']] if base.get('embedding') else []) + [e['embedding'] for e in entries]
    return {
        BASE_KEY: dict(base),
        POOL_KEY: list(entries),
        'speaker_embedding': pool_owner_vectors(vectors) if vectors else None,
        'speech_samples': list(base.get('samples') or []) + [e['sample_path'] for e in entries],
        'speech_sample_transcripts': list(base.get('transcripts') or []) + [e['transcript'] for e in entries],
        'speech_samples_version': 3,
        'speech_sample_source': entries[-1]['source'] if entries else base.get('source'),
    }


def pool_profile(person: Mapping, profile: Mapping) -> tuple[dict, list[str]]:
    """One contribution per conversation; duplicates replace rather than amplify it."""
    base = dict(person.get(BASE_KEY) or {})
    entries = list(person.get(POOL_KEY) or [])
    if person.get(BASE_KEY) is None and person.get(POOL_KEY) is None and usable_person_voiceprint(person):
        source = person.get('speech_sample_source') or {}
        if source.get('conversation_id') and len(person.get('speech_samples') or []) == 1:
            entries.append(
                {
                    'embedding': person['speaker_embedding'],
                    'sample_path': person['speech_samples'][0],
                    'transcript': (person.get('speech_sample_transcripts') or [''])[0],
                    'source': source,
                }
            )
        elif not source:
            base = {
                'embedding': person['speaker_embedding'],
                'samples': person.get('speech_samples') or [],
                'transcripts': person.get('speech_sample_transcripts') or [],
            }
    source = profile['speech_sample_source']
    entries = [e for e in entries if e['source'].get('conversation_id') != source.get('conversation_id')]
    entries.append(
        {
            'embedding': profile['speaker_embedding'],
            'sample_path': profile['speech_samples'][0],
            'transcript': profile['speech_sample_transcripts'][0],
            'source': source,
        }
    )
    entries = entries[-MAX_CONTRIBUTIONS:]
    update = {**profile, **_materialize(base, entries)}
    removed = [path for path in person.get('speech_samples') or [] if path not in update['speech_samples']]
    return update, removed


def retract_profile(
    person: Mapping, conversation_ids: Sequence[str], segment_ids: Sequence[str]
) -> tuple[dict, list[str]]:
    """Undo only intersecting contributions, also after the serving flag is rolled back."""
    if person.get(POOL_KEY) is None:
        return {}, []
    entries = list(person.get(POOL_KEY) or [])
    ids, segments = set(conversation_ids), set(segment_ids)
    kept = [
        e
        for e in entries
        if e['source'].get('conversation_id') not in ids
        or not segments.intersection(e['source'].get('segment_ids') or [])
    ]
    if len(kept) == len(entries):
        return {}, []
    update = _materialize(person.get(BASE_KEY) or {}, kept)
    return update, [p for p in person.get('speech_samples') or [] if p not in update['speech_samples']]


def remove_sample(person: Mapping, sample_path: str) -> dict:
    """Audio deletion retracts its vector too, even when other samples remain."""
    if person.get(POOL_KEY) is None:
        return {}
    base = dict(person.get(BASE_KEY) or {})
    if sample_path in (base.get('samples') or []):
        # A pre-pool base has no per-clip vectors; remove its authority as a unit.
        base['embedding'] = None
        pairs = [(p, t) for p, t in zip(base.get('samples') or [], base.get('transcripts') or []) if p != sample_path]
        base['samples'] = [p for p, _ in pairs]
        base['transcripts'] = [t for _, t in pairs]
    return _materialize(base, [e for e in person.get(POOL_KEY) or [] if e['sample_path'] != sample_path])
