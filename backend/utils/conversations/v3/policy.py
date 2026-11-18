"""Pure v3 intent policy shared by projection, processing and on-open notes."""

from collections.abc import Mapping
from utils.conversations.processing_trigger import ProcessingTrigger


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
