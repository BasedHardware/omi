"""Default-on repair within the already admitted authoritative batch cohort."""

from config.refactor_modes import default_on

BATCH_CONVERSATION_SPEAKERS_ENV = 'BATCH_CONVERSATION_SPEAKERS_ENABLED'
BATCH_CONVERSATION_SCOPE = 'final:batch:conversation:'
SYNC_OFF_CENTROIDS_ENV = 'BATCH_SYNC_OFF_CENTROIDS_ENABLED'
VENDOR_SPEAKER_TURNS_ENV = 'BATCH_VENDOR_SPEAKER_TURNS_ENABLED'


def sync_off_enabled() -> bool:
    return default_on(BATCH_CONVERSATION_SPEAKERS_ENV) and default_on(SYNC_OFF_CENTROIDS_ENV)


def vendor_turns_enabled() -> bool:
    # Off restores words-only vendor units (unit-local `sync:` labels) at every
    # read site, including results already committed with vendor turns.
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
