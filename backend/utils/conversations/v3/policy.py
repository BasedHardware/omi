"""Pure v3 intent policy shared by projection, processing and on-open notes."""

from collections.abc import Mapping
from datetime import datetime, timedelta

from utils.conversations.fragment_visibility import BATCH_RECORD_OWNERS
from utils.conversations.processing_trigger import ProcessingTrigger

# Listen seals a live v3 recording at a pause this long (config/conversations_v3.py rotation_seconds).
ROTATION_PAUSE_SECONDS = 1.5
LIVE_SUMMARY_FIELD = 'v3_live_summary'
LIVE_TITLE_STATE = 'v3_live_title_state'
# Stamped on a recording that rotation sealed: the listen hard cap in force, in seconds.
ROTATION_CAP_FIELD = 'v3_rotation_cap_seconds'
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
