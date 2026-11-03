"""Default-on recording naming capability and hard request budgets."""

from config.refactor_modes import default_on

RECORDING_SPEAKER_RENAME_ENABLED_ENV = 'RECORDING_SPEAKER_RENAME_ENABLED'
MAX_MEMBERS = 64
MAX_SEGMENTS = 10000
MAX_SCOPES = 30
SCOPE_INDEX_FIELD = 'recording_speaker_scopes'


def enabled():
    return default_on(RECORDING_SPEAKER_RENAME_ENABLED_ENV)


class RecordingLimitExceeded(Exception):
    """No writes were attempted; the client can ask for fewer selected lines."""


def check_budget(member_count, segment_count=0):
    if member_count > MAX_MEMBERS or segment_count > MAX_SEGMENTS:
        raise RecordingLimitExceeded('Recording is too large. Select fewer lines in one conversation.')


def stamp_scope_index(data):
    segments = data.get('transcript_segments')
    if isinstance(segments, list):
        data[SCOPE_INDEX_FIELD] = sorted({s['speaker_id_scope'] for s in segments if s.get('speaker_id_scope')})
