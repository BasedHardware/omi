"""Reversible person voiceprint contributions. Pure; publication fences live in DB."""

from typing import Any, Mapping, Sequence, NoReturn
from math import isfinite
import logging

from prometheus_client import Counter
from config.refactor_modes import serving_for, shadow_or_serve

from utils.owner_voice_evidence import pool_owner_vectors
from utils.stt.voiceprints import usable_person_voiceprint
from utils.speakers import policy
from utils.speakers.refinement import unit
from utils.observability.fallback import record_fallback
from utils.observability.reasons import PersonVoiceQualityReason, ReasonFamily, reason_label

MAX_CONTRIBUTIONS = 5
POOL_KEY = 'person_voice_confirmations'
BASE_KEY = 'person_voice_base'
logger = logging.getLogger(__name__)
QUALITY = Counter('omi_speaker_evidence_person_sample_total', 'Pooled person sample quality', ['outcome'])


class PersonVoiceQualityError(ValueError):
    pass


def reject(reason: str) -> NoReturn:
    QUALITY.labels(outcome=reason_label(ReasonFamily.SPEAKER_EVIDENCE, reason, PersonVoiceQualityReason)).inc()
    logger.info('event=refactor_shadow lane=L2 check=person_sample_quality outcome=disagree')
    raise PersonVoiceQualityError(reason)


def shadow_profile(uid, person, profile):
    """Compare without changing the legacy transaction or its sample cleanup."""
    if shadow_or_serve('SPEAKER_EVIDENCE_MODE') and not serving_for('SPEAKER_EVIDENCE_MODE', uid):
        try:
            proposed, _ = pool_profile(person, profile)
            agrees = proposed['speaker_embedding'] == profile.get('speaker_embedding')
        except PersonVoiceQualityError:
            agrees = False
        except Exception as error:
            QUALITY.labels(outcome='error').inc()
            logger.warning(
                'event=refactor_shadow lane=L2 check=person_pool outcome=error exception_type=%s', type(error).__name__
            )
            record_fallback(
                component='other',
                from_mode='person_pool_shadow',
                to_mode='legacy_profile',
                reason='other',
                outcome='degraded',
                log=logger,
            )
            return
        logger.info('event=refactor_shadow lane=L2 check=person_pool outcome=%s', 'agree' if agrees else 'disagree')


def _materialize(base: Mapping, entries: Sequence[Mapping]) -> dict[str, Any]:
    vectors = ([base['embedding']] if base.get('embedding') else []) + [e['embedding'] for e in entries]
    # Cosine embeddings have arbitrary magnitude. Normalize each contribution
    # before averaging so a single high-norm clip cannot replace enrollment.
    vectors = [vector.tolist() for v in vectors if (vector := unit(v)) is not None]
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
    incoming = unit(profile.get('speaker_embedding'))
    if incoming is None:
        reject('invalid_person_voiceprint')
    seconds = profile.get('voice_speech_seconds')
    if seconds is not None and (
        not isinstance(seconds, (int, float)) or not isfinite(seconds) or seconds < policy.MIN_EVIDENCE_SECONDS
    ):
        reject('insufficient_person_voice_audio')
    existing = unit(usable_person_voiceprint(person))
    if existing is not None and (
        incoming.shape != existing.shape or not policy.ENROLLED_PERSON.accepts(float(1 - incoming @ existing))
    ):
        reject('incompatible_person_voiceprint')
    profile = {**profile, 'speaker_embedding': incoming.tolist()}
    base: dict[str, Any] = dict(person.get(BASE_KEY) or {})
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
        else:
            # Preserve a legacy aggregate with multiple clips as one base; no
            # per-clip vectors exist to split its authority safely.
            base = {
                'embedding': person['speaker_embedding'],
                'samples': person.get('speech_samples') or [],
                'transcripts': person.get('speech_sample_transcripts') or [],
                'source': source or None,
            }
    source = profile['speech_sample_source']
    if source.get('conversation_id') and (base.get('source') or {}).get('conversation_id') == source.get(
        'conversation_id'
    ):
        base = {}  # One legacy aggregate contribution is replaced as a unit.
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
    QUALITY.labels(outcome='accepted').inc()
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
    base = person.get(BASE_KEY) or {}
    source = base.get('source') or {}
    retract_base = source.get('conversation_id') in ids and bool(segments.intersection(source.get('segment_ids') or []))
    if len(kept) == len(entries) and not retract_base:
        return {}, []
    update = _materialize({} if retract_base else base, kept)
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
