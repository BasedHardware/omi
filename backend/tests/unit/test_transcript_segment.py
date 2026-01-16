import pytest

from models.transcript_segment import TranscriptSegment


def _segment(text, speaker="SPEAKER_00", is_user=False, start=0.0, end=1.0):
    return TranscriptSegment(text=text, speaker=speaker, is_user=is_user, start=start, end=end)


def test_forward_merge_on_short_incomplete_last_sentence():
    a = _segment("Hello there. and then", speaker="SPEAKER_00", start=0.0, end=4.0)
    b = _segment("we continue speaking.", speaker="SPEAKER_01", start=4.0, end=7.0)

    segments, _ = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert segments[0].text == "Hello there."
    assert segments[0].end == pytest.approx(4.0)
    assert segments[1].speaker == "SPEAKER_01"
    assert segments[1].text == "and then we continue speaking."


def test_no_forward_merge_when_incomplete_is_longer_than_next_segment():
    a = _segment("and then we continue speaking", speaker="SPEAKER_00", start=0.0, end=3.0)
    b = _segment("ok.", speaker="SPEAKER_01", start=3.0, end=4.0)

    segments, _ = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert segments[0].text == "and then we continue speaking"
    assert segments[1].text == "ok."


def test_merge_same_speaker_with_small_gap():
    a = _segment("Hello", speaker="SPEAKER_00", start=0.0, end=1.0)
    b = _segment("world.", speaker="SPEAKER_00", start=1.1, end=2.0)

    segments, _ = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 1
    assert segments[0].text == "Hello world."


def test_forward_merge_trims_completed_prefix():
    a = _segment("First sentence. trailing", speaker="SPEAKER_00", start=0.0, end=4.0)
    b = _segment("continue here.", speaker="SPEAKER_01", start=4.0, end=6.0)

    segments, _ = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert segments[0].text == "First sentence."
    assert segments[1].text == "trailing continue here."


def test_forward_merge_drops_segment_when_only_incomplete():
    a = _segment("unfinished", speaker="SPEAKER_00", start=0.0, end=2.0)
    b = _segment("continues now.", speaker="SPEAKER_01", start=2.0, end=4.0)

    segments, _ = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 1
    assert segments[0].speaker == "SPEAKER_01"
    assert segments[0].text == "unfinished continues now."


def test_lowercase_continuation_only_merges_same_speaker():
    a = _segment("hello", speaker="SPEAKER_00", start=0.0, end=1.0)
    b = _segment("world", speaker="SPEAKER_01", start=1.2, end=2.0)

    segments, _ = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
