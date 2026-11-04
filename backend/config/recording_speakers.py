"""Default-on recording naming capability and hard request budgets."""

from config.refactor_modes import default_on

RECORDING_SPEAKER_RENAME_ENABLED_ENV = 'RECORDING_SPEAKER_RENAME_ENABLED'
MAX_MEMBERS = 64
MAX_SEGMENTS = 10000
MAX_SCOPES = 30
SCOPE_INDEX_FIELD = 'recording_speaker_scopes'
SCOPE_INDEX_AT_CREATION_FIELD = 'recording_speaker_scopes_at_creation'


def enabled():
    return default_on(RECORDING_SPEAKER_RENAME_ENABLED_ENV)


class RecordingLimitExceeded(Exception):
    """No writes were attempted; the client can ask for fewer selected lines."""


def check_budget(member_count, segment_count=0):
    if member_count > MAX_MEMBERS or segment_count > MAX_SEGMENTS:
        raise RecordingLimitExceeded('Recording is too large. Select fewer lines in one conversation.')


def stamp_scope_index(data):
    # Provenance is server-owned. Ordinary writes and rename repairs must never
    # promote an old recording into one whose membership was indexed at birth.
    data.pop(SCOPE_INDEX_AT_CREATION_FIELD, None)
    segments = data.get('transcript_segments')
    if isinstance(segments, list):
        data[SCOPE_INDEX_FIELD] = sorted({s['speaker_id_scope'] for s in segments if s.get('speaker_id_scope')})


def with_creation_scope_index(data):
    """Call only after a transaction proves the conversation does not exist.

    The write encoder has already indexed the plaintext transcript, including
    an empty live transcript. Later writes maintain that index. A rename can
    repair an older row's index but cannot supply this creation-time proof.
    """
    data = dict(data)
    data.pop(SCOPE_INDEX_AT_CREATION_FIELD, None)
    if isinstance(data.get(SCOPE_INDEX_FIELD), list):
        data[SCOPE_INDEX_AT_CREATION_FIELD] = True
    return data
