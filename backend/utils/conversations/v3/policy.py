"""Pure v3 intent policy shared by projection, processing and on-open notes."""

from collections.abc import Mapping
from utils.conversations.processing_trigger import ProcessingTrigger


def field(row, name):
    return row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)


def manual_intent(row):
    return bool(
        field(row, 'v3_derived') and field(row, 'manual_end') and field(row, 'kind') not in {'media', 'background'}
    )


def explicit_retry(row, trigger):
    return bool(field(row, 'v3_derived') and trigger == ProcessingTrigger.USER_REPROCESS)


def full_notes(row, trigger=ProcessingTrigger.CAPTURE_END):
    return manual_intent(row) or explicit_retry(row, trigger)


def transcription_failed(row):
    # A partial/unproven tail is still recoverable; only explicit failure receipts close it.
    return bool(
        field(row, 'status') == 'failed'
        or field(row, 'record_upload_failed')
        or field(row, 'finalization_status') == 'dead_letter'
    )
