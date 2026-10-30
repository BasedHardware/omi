"""Default-on repair within the already admitted authoritative batch cohort."""

from config.refactor_modes import default_on

BATCH_CONVERSATION_SPEAKERS_ENV = 'BATCH_CONVERSATION_SPEAKERS_ENABLED'
BATCH_CONVERSATION_SCOPE = 'final:batch:conversation:'
SYNC_OFF_CENTROIDS_ENV = 'BATCH_SYNC_OFF_CENTROIDS_ENABLED'


def sync_off_enabled() -> bool:
    return default_on(BATCH_CONVERSATION_SPEAKERS_ENV) and default_on(SYNC_OFF_CENTROIDS_ENV)


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
