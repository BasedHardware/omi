"""Default-on repair within the already admitted authoritative batch cohort."""

import math
import os

from config.refactor_modes import default_on
from config.policy.batch import COHORT_SALTS, cohort_bucket

BATCH_CONVERSATION_SPEAKERS_ENV = 'BATCH_CONVERSATION_SPEAKERS_ENABLED'
BATCH_FINAL_PASS_ENV = 'BATCH_FINAL_PASS_ENABLED'
BATCH_CONVERSATION_SCOPE = 'final:batch:conversation:'
SYNC_OFF_CENTROIDS_ENV = 'BATCH_SYNC_OFF_CENTROIDS_ENABLED'
VENDOR_SPEAKER_TURNS_ENV = 'BATCH_VENDOR_SPEAKER_TURNS_ENABLED'


def _default_on(name: str) -> bool:
    """Keep the shared parser and expose constant-named kill-switch reads to deployment checks."""
    return default_on(name)


def sync_off_enabled() -> bool:
    return default_on(BATCH_CONVERSATION_SPEAKERS_ENV) and default_on(SYNC_OFF_CENTROIDS_ENV)


def vendor_turns_enabled() -> bool:
    # Off: new and replayed projections are words-only (`sync:` labels) and no
    # resolver reads vendor evidence. Like centroid expiry, it does not regroup
    # or rename conversations already resolved; that would rewrite user data.
    return default_on(VENDOR_SPEAKER_TURNS_ENV)


VENDOR_SPEAKER_PROVIDERS = frozenset({'modulate', 'soniox'})


def vendor_evidence_refused(segment) -> bool:
    """With the switch off, a vendor unit's batch authority is not read: no vectors, no must-links.

    The original unit partition survives resolution in ``provider_speaker``.
    """
    if vendor_turns_enabled():
        return False
    original = segment.provider_speaker or {}
    scope = original.get('scope') or segment.speaker_id_scope or ''
    provider = original.get('provider') or segment.stt_provider
    return (
        provider in VENDOR_SPEAKER_PROVIDERS
        and scope.startswith('final:batch:')
        and not scope.startswith(BATCH_CONVERSATION_SCOPE)
    )


def vendor_speaker_authority(payload) -> bool:
    """A vendor-route result whose own unit-local speaker turns stand in for pyannote's."""
    return (
        payload.get('recovery_version') == 1
        and bool((payload.get('diarization') or {}).get('turns'))
        and vendor_turns_enabled()
    )


def has_batch_authority(segments) -> bool:
    # Resolution changes public scopes; the original partition survives in the
    # internal provider marker so retries cannot fall back to unconstrained AHC.
    return any(
        (s.speaker_id_scope or '').startswith('final:batch:')
        or ((s.provider_speaker or {}).get('scope') or '').startswith('final:batch:')
        for s in segments
    )


def enabled(segments) -> bool:
    return has_batch_authority(segments) and default_on(BATCH_CONVERSATION_SPEAKERS_ENV)


def batch_unit_scope(segment) -> str | None:
    """Original batch unit namespace: one opaque ID, never a lane or conversation."""
    scope = (segment.provider_speaker or {}).get('scope') or segment.speaker_id_scope or ''
    prefix = 'final:batch:'
    unit = scope.removeprefix(prefix)
    return scope if scope.startswith(prefix) and 0 < len(unit) <= 128 and ':' not in unit and '/' not in unit else None


def _final_pass_admitted(uid: str, segments) -> bool:
    """Shared rollout admission, including already resolved batch conversations."""
    if not uid or not enabled(segments) or not _default_on(BATCH_FINAL_PASS_ENV):
        return False
    try:
        percent = float(os.getenv('BATCH_FINAL_PASS_PERCENT', '100'))
        return math.isfinite(percent) and cohort_bucket(uid, COHORT_SALTS['transcription-final-pass']) < max(
            0, min(100, percent)
        )
    except ValueError:
        return False


def final_pass_enabled_for(uid: str, segments) -> bool:
    """Audio reconstruction additionally requires an original batch unit."""
    return _final_pass_admitted(uid, segments) and any(batch_unit_scope(s) for s in segments)


def recurring_enabled_for(uid: str, segments) -> bool:
    """Default-on private learning; reuse the final-pass UID hash, nested admission."""
    if not _final_pass_admitted(uid, segments) or not default_on('SPEAKER_RECURRING_VOICES_ENABLED'):
        return False
    try:
        percent = float(os.getenv('SPEAKER_RECURRING_PERCENT', '100'))
        return math.isfinite(percent) and cohort_bucket(uid, COHORT_SALTS['transcription-final-pass']) < max(
            0, min(100, percent)
        )
    except ValueError:
        return False
