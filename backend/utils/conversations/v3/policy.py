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
