"""Counts-only triage and immutable historical delivery policy."""

import math
from types import SimpleNamespace

import pytest

from utils.conversations.backfill_stats import transcript_stats, classify
from utils.conversations.processing_trigger import (
    ProcessingTrigger,
    PROCESSING_MODES,
    RelevancePolicy,
    trigger_for_finalization_job,
)
from database import stuck_backfill as backfill


def test_union_unicode_words_and_speakers():
    stats = transcript_stats(
        [
            {'start': 0, 'end': 10, 'speaker': 'a', 'text': 'hello thế giới'},
            {'start': 5, 'end': 15, 'speaker': 'b', 'text': 'two words'},
            {'start': 30, 'end': 35, 'speaker': 'a', 'text': ''},
            {'start': math.nan, 'end': 90, 'text': ''},
        ]
    )
    assert stats == {'speech_seconds': 20, 'word_count': 5, 'segment_count': 4, 'speaker_count': 2}
    assert classify(stats, False, seconds=20, words=30) == 'substantive'
    assert classify(stats, False, seconds=60, words=100) == 'noise'


def test_audio_without_transcript_and_malformed_are_never_noise():
    assert classify(transcript_stats([]), True, seconds=60, words=100) == 'review_audio_without_transcript'
    with pytest.raises(ValueError):
        transcript_stats([None])
    with pytest.raises(ValueError):
        transcript_stats([{'text': 42}])


def test_immutable_policy_survives_job_roundtrip_and_retries():
    job = {'processing_trigger': 'silent_backfill', 'delivery_policy': 'silent_backfill_v1'}
    for retry in range(4):
        assert trigger_for_finalization_job({**job, 'attempt_count': retry}) is ProcessingTrigger.SILENT_BACKFILL
    mode = PROCESSING_MODES[ProcessingTrigger.SILENT_BACKFILL]
    assert mode.run_now and mode.reprocess and mode.relevance is RelevancePolicy.KEEP
    assert trigger_for_finalization_job({'force_process': True}) is ProcessingTrigger.CLIENT_FINALIZE


@pytest.mark.parametrize(
    'job',
    [
        {'processing_trigger': 'silent_backfill'},
        {'processing_trigger': 'server_recovery', 'delivery_policy': 'silent_backfill_v1'},
        {'processing_trigger': 'silent_backfill', 'delivery_policy': 'unknown'},
    ],
)
def test_invalid_historical_policy_fails_closed(job):
    with pytest.raises(ValueError):
        trigger_for_finalization_job(job)


def test_revision_retains_nanoseconds():
    from google.api_core.datetime_helpers import DatetimeWithNanoseconds

    stamp = '2026-10-22T05:15:00.123456789Z'
    assert backfill.revision(SimpleNamespace(update_time=DatetimeWithNanoseconds.from_rfc3339(stamp))) == stamp


def test_row_revision_fence_does_not_round_away_nanoseconds():
    from google.api_core.datetime_helpers import DatetimeWithNanoseconds
    from utils.conversations.backfill_stats import same_timestamp_revision

    before = DatetimeWithNanoseconds.from_rfc3339('2026-10-22T05:15:00.123456001Z')
    changed = DatetimeWithNanoseconds.from_rfc3339('2026-10-22T05:15:00.123456999Z')
    assert before == changed  # Python datetime's misleading equality is the regression.
    assert not same_timestamp_revision(before, changed)
    assert same_timestamp_revision(before, before)


def test_empty_text_with_audio_stays_review_even_with_long_segment_timestamps():
    stats = transcript_stats([{'text': '', 'start': 0, 'end': 120}])
    assert classify(stats, True, seconds=60, words=100) == 'review_audio_without_transcript'
