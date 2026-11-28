"""Pure v3 intent policy shared by projection, processing and on-open notes."""

from collections.abc import Mapping
import math
from datetime import datetime, timedelta

from utils.conversations.fragment_visibility import BATCH_RECORD_OWNERS
from utils.conversations.processing_trigger import ProcessingTrigger

# Listen seals a live v3 recording at a pause this long (config/conversations_v3.py rotation_seconds).
ROTATION_PAUSE_SECONDS = 1.5
LIVE_SUMMARY_FIELD = 'v3_live_summary'
LIVE_TITLE_STATE = 'v3_live_title_state'
# Stamped on a recording that rotation sealed: the listen hard cap in force, in seconds.
ROTATION_CAP_FIELD = 'v3_rotation_cap_seconds'
NATIVE_MANUAL_STOP = 'v3_native_manual_stop'
NATIVE_MANUAL_INPUT_REVISION = 'v3_native_manual_input_revision'
NATIVE_MANUAL_READY = 'v3_native_manual_ready_revision'
NATIVE_MANUAL_PROOF = 'v3_native_manual_ready_proof'
NATIVE_MANUAL_BINDING = 'v3_native_manual_binding'
NATIVE_MANUAL_NOTES_VISIBILITY = 'v3_native_manual_notes_visibility'
NATIVE_MANUAL_SETTLED = 'v3_native_manual_settled'
NATIVE_MANUAL_SOURCE_FIELDS = (
    NATIVE_MANUAL_STOP,
    NATIVE_MANUAL_READY,
    NATIVE_MANUAL_PROOF,
    'v3_manual_end',
    'finished_at',
    'finalization_job_id',
    'finalization_revision',
    'record_lane_owner',
    'record_upload_revision',
    'record_sealed_at',
    'record_audio_closed',
    'record_upload_sessions',
    'record_audio_partial',
    'record_upload_failed',
    'private_cloud_sync_enabled',
    'uses_custom_stt',
    'status',
    'discarded',
)
# How long a sealed recording's pending transcript keeps the previous stretch open.
TRANSCRIPT_WAIT = timedelta(minutes=15)
# How long a manual-end cut waits for the batch transcript of its own or a preceding sealed recording.
# Equal to the default lock delay: a Finish never settles later than the same speech would without one.
FINISH_WAIT = timedelta(minutes=5)


def live_title_candidate(row):
    return (
        row.get('v3_derived') is True
        and row.get('status') == 'in_progress'
        and row.get('tile_state') == 'live'
        and row.get('data_protection_level') not in {'private', 'e2ee'}
        and not any(
            row.get(field)
            for field in (
                'deleted',
                'discarded',
                'is_locked',
                'backfilled',
                'title_locked',
                'home_content_invalidated',
                'home_hidden',
            )
        )
        and not str(row.get('user_title') or '').strip()
        and not str((row.get('structured') or {}).get('title') or '').strip()
    )


def live_summary_target(row):
    return (
        row.get('v3_derived') is True
        and row.get('status') == 'in_progress'
        and isinstance(row.get('started_at'), datetime)
        and isinstance(row.get('finished_at'), datetime)
        and row.get('data_protection_level') not in {'private', 'e2ee'}
        and not any(
            row.get(key)
            for key in ('recording', 'discarded', 'deleted', 'is_locked', 'home_hidden', 'sync_merged_into')
        )
    )


def field(row, name):
    return row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)


def flag(row, name):
    """A v3 boolean marker is set only when it is literally True (never a truthy stand-in)."""
    return field(row, name) is True


def native_manual_binding(row, *, recording_id=None):
    """Bind manual notes to the same sealed upload and explicit stop that completed projection."""
    intent = row.get(NATIVE_MANUAL_STOP)
    upload_revision = row.get(NATIVE_MANUAL_READY)
    sealed_at = row.get('record_sealed_at')
    finished_at = row.get('finished_at')
    cid = recording_id or row.get('id')
    finalization_revision = row.get('finalization_revision')
    if (
        not isinstance(cid, str)
        or not cid
        or '/' in cid
        or not isinstance(intent, Mapping)
        or not finished_at
        or intent.get('finished_at') != finished_at
        or not intent.get('job_id')
        or intent.get('job_id') != row.get('finalization_job_id')
        or type(finalization_revision) is not int
        or finalization_revision < 1
        or intent.get('revision') != finalization_revision
        or type(upload_revision) is not int
        or upload_revision < 1
        or type(row.get('record_upload_revision')) is not int
        or row.get('record_upload_revision') != upload_revision
        or type(sealed_at) not in (int, float)
        or not math.isfinite(sealed_at)
        or sealed_at <= 0
        or row.get(NATIVE_MANUAL_PROOF) != {'seal': sealed_at, 'intent': intent}
        or row.get('recording') is not True
        or row.get('v3_manual_end') is not True
        or row.get('status') != 'completed'
        or row.get('record_lane_owner') != 'batch_live_v1'
        or row.get('record_audio_closed') is not True
        or row.get('private_cloud_sync_enabled') is not True
        or row.get('data_protection_level') not in {'standard', 'enhanced'}
        or any(
            row.get(key)
            for key in (
                'deleted',
                'discarded',
                'sync_merged_into',
                'is_locked',
                'uses_custom_stt',
                'record_upload_sessions',
                'record_upload_failed',
                'record_audio_partial',
            )
        )
    ):
        return None
    return {
        'recording_id': cid,
        'upload_revision': upload_revision,
        'sealed_at': sealed_at,
        'finished_at': finished_at,
        'finalization_revision': finalization_revision,
    }


def native_manual_notes_window(row, recording_id):
    """The exact derived window where validated native notes became visible."""
    if (
        not row.get('id')
        or not row.get('started_at')
        or not row.get('finished_at')
        or not recording_id
        or recording_id not in (row.get('v3_recording_ids') or [])
    ):
        return None
    return {
        'conversation_id': row['id'],
        'recording_id': recording_id,
        'started_at': row['started_at'],
        'finished_at': row['finished_at'],
    }


def native_manual_notes_receipt(row):
    """Call only alongside the notes write after the raw source passed its fence."""
    binding = row.get(NATIVE_MANUAL_BINDING)
    if (
        isinstance(binding, Mapping)
        and manual_intent(row)
        and row.get('home_hidden') is False
        and not any(row.get(key) for key in ('deleted', 'discarded', 'is_locked'))
    ):
        return native_manual_notes_window(row, binding.get('recording_id'))
    return None


def manual_intent(row):
    return bool(
        flag(row, 'v3_derived') and flag(row, 'manual_end') and field(row, 'kind') not in {'media', 'background'}
    )


def explicit_retry(row, trigger):
    return bool(flag(row, 'v3_derived') and trigger == ProcessingTrigger.USER_REPROCESS)


def full_notes(row, trigger=ProcessingTrigger.CAPTURE_END):
    return manual_intent(row) or explicit_retry(row, trigger)


def transcription_pending(row):
    """A partial-recording repair still has audio to transcribe.

    The partial marker stays on the recording after its coordinator settles, so its presence alone
    is not pending work. Runs number their generations from 1: nothing is planned yet at 0, and a
    planned generation is outstanding until it is applied.
    """
    mark = field(row, 'record_audio_partial')
    if not isinstance(mark, Mapping):
        return False
    generation = int(mark.get('generation') or 0)
    return generation == 0 or int(mark.get('applied_generation') or 0) < generation


def transcription_failed(row):
    # A partial/unproven tail is still recoverable; only explicit failure receipts close it.
    return bool(
        field(row, 'status') == 'failed'
        or field(row, 'record_upload_failed')
        or field(row, 'finalization_status') == 'dead_letter'
    )


def created_eligible(row):
    """A visible, completed, notes-bearing derived row owes one conversation-created delivery.

    Mirrors the legacy suppressions: discarded, locked, recordings, free-tier terminal minimums
    (terminal_no_derived_effects) and silent backfill never fan out; hidden rows wait for visibility.
    """
    return bool(
        row
        and row.get('v3_derived')
        and row.get('v3_notes_written')
        and not row.get('recording')
        and not row.get('deleted')
        and not row.get('discarded')
        and not row.get('is_locked')
        and not row.get('home_hidden')
        and not row.get('backfilled')
        and not row.get('terminal_no_derived_effects')
        and row.get('data_protection_level') != 'private'
        and not row.get('v3_process_failed')
        and row.get('status') == 'completed'
        and not row.get('v3_created_delivered_at')
    )


def builder_eligible(row):
    """A source recording the builder places into stretches (live and backfill passes alike)."""
    return bool(
        row
        and row.get('recording')
        and not row.get('deleted')
        and not row.get('discarded')
        and not row.get('sync_merged_into')
        and row.get('data_protection_level') != 'private'
        and row.get('started_at')
        and not row.get('_v3_unreadable')
    )


def awaiting_batch_transcript(row):
    """A sealed batch recording whose transcript has not landed: its audio may hold speech.

    The batch projection receipt (``record_projection_revision``) marks a landed transcript, empty or
    not; a provisional (fast-finish) transcript shows as segments. Failure receipts end the wait.
    """
    return bool(
        flag(row, 'recording')
        and field(row, 'record_lane_owner') in BATCH_RECORD_OWNERS
        and field(row, 'status') in {'processing', 'completed'}
        and not field(row, 'record_projection_revision')
        and not field(row, 'transcript_segments')
        and not transcription_failed(row)
        and not any(field(row, key) for key in ('deleted', 'discarded', 'sync_merged_into'))
        and field(row, 'data_protection_level') != 'private'
    )


def awaiting_transcript(row, now, cap_seconds):
    """A recording whose transcript has not landed yet: missing transcript is not silence.

    Bounded, so a stuck row cannot hold the previous stretch open: a live row that is past the
    rotation cap has heard no speech (it would have sealed), and a sealed row waits TRANSCRIPT_WAIT.
    """
    status = field(row, 'status')
    if status == 'processing':
        since = field(row, 'finished_at') or field(row, 'started_at')
        return since is not None and now - since < TRANSCRIPT_WAIT
    if status == 'in_progress':
        created = field(row, 'created_at') or field(row, 'started_at')
        return created is not None and now - created < timedelta(seconds=cap_seconds + 15)
    return False


def processing_due(row, now):
    retry_at = row.get('v3_process_retry_after')
    return not isinstance(retry_at, datetime) or retry_at <= now
