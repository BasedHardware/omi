import pytest

from models.transcript_segment import TranscriptSegment


def _segment(text, speaker="SPEAKER_00", is_user=False, start=0.0, end=1.0):
    return TranscriptSegment(text=text, speaker=speaker, is_user=is_user, start=start, end=end)


def _concat_texts(texts):
    return " ".join(text.strip() for text in texts if text).strip()


def _concat_segments(segments):
    return _concat_texts([segment.text for segment in segments])


def _normalize_punctuation(text):
    return text.strip().replace("  ", " ").replace(" ,", ",").replace(" .", ".").replace(" ?", "?")


def test_forward_merge_on_short_incomplete_last_sentence():
    a = _segment("Hello there. and then", speaker="SPEAKER_00", start=0.0, end=4.0)
    b = _segment("we continue speaking.", speaker="SPEAKER_01", start=4.0, end=7.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, _, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert segments[0].text == "Hello there."
    assert segments[0].end == pytest.approx(4.0)
    assert segments[1].speaker == "SPEAKER_01"
    assert segments[1].text == "and then we continue speaking."
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_no_forward_merge_when_incomplete_is_longer_than_next_segment():
    a = _segment("and then we continue speaking", speaker="SPEAKER_00", start=0.0, end=3.0)
    b = _segment("Ok.", speaker="SPEAKER_01", start=3.0, end=4.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, _, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert segments[0].text == "and then we continue speaking"
    assert segments[1].text == "Ok."
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_merge_same_speaker_with_small_gap():
    a = _segment("Hello", speaker="SPEAKER_00", start=0.0, end=1.0)
    b = _segment("world.", speaker="SPEAKER_00", start=1.1, end=2.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, _, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 1
    assert segments[0].text == "Hello world."
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_updated_segments_returned_for_existing_merge():
    existing = _segment("Hello", speaker="SPEAKER_00", start=0.0, end=1.0)
    new = _segment("world.", speaker="SPEAKER_00", start=1.1, end=2.0)
    input_concat = _concat_texts([existing.text, new.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([existing], [new])

    assert len(segments) == 1
    assert segments[0].text == "Hello world."
    assert len(updated_segments) == 1
    assert updated_segments[0].id == existing.id
    assert updated_segments[0].text == "Hello world."
    assert removed_ids == []
    assert existing.id not in removed_ids
    assert new.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_forward_merge_trims_completed_prefix():
    a = _segment("First sentence. trailing", speaker="SPEAKER_00", start=0.0, end=4.0)
    b = _segment("continue here.", speaker="SPEAKER_01", start=4.0, end=6.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert segments[0].text == "First sentence."
    assert segments[1].text == "trailing continue here."
    assert len(updated_segments) == 2
    assert updated_segments[0].text == "First sentence."
    assert updated_segments[1].text == "trailing continue here."
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_forward_merge_preserves_prefix_when_tail_incomplete_multi_sentence():
    a = _segment("First sentence. trailing", speaker="SPEAKER_00", start=0.0, end=4.0)
    b = _segment("continues here with more.", speaker="SPEAKER_01", start=4.0, end=6.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert segments[0].speaker == "SPEAKER_00"
    assert segments[0].text == "First sentence."
    assert segments[1].speaker == "SPEAKER_01"
    assert segments[1].text == "trailing continues here with more."
    assert len(updated_segments) == 2
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_forward_merge_drops_segment_when_only_incomplete():
    a = _segment("unfinished", speaker="SPEAKER_00", start=0.0, end=2.0)
    b = _segment("continues now.", speaker="SPEAKER_01", start=2.0, end=4.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 1
    assert segments[0].speaker == "SPEAKER_01"
    assert segments[0].text == "unfinished continues now."
    assert len(updated_segments) == 1
    assert updated_segments[0].speaker == "SPEAKER_01"
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_forward_merge_drops_existing_tail_segment():
    existing = _segment("we're", speaker="SPEAKER_02", start=0.0, end=1.0)
    new = _segment("we're struggling to connect.", speaker="SPEAKER_01", start=1.2, end=3.0)
    input_concat = _concat_texts([existing.text, new.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([existing], [new])

    assert len(segments) == 1
    assert segments[0].speaker == "SPEAKER_01"
    assert segments[0].text == "we're we're struggling to connect."
    assert len(updated_segments) == 1
    assert updated_segments[0].speaker == "SPEAKER_01"
    assert removed_ids == [existing.id]
    assert new.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_forward_merge_deletes_segment_when_only_incomplete_and_longer_next():
    existing = _segment("unfinished", speaker="SPEAKER_00", start=0.0, end=1.0)
    new = _segment("unfinished but continues here.", speaker="SPEAKER_01", start=1.1, end=3.0)
    input_concat = _concat_texts([existing.text, new.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([existing], [new])

    assert len(segments) == 1
    assert segments[0].speaker == "SPEAKER_01"
    assert segments[0].text == "unfinished unfinished but continues here."
    assert len(updated_segments) == 1
    assert updated_segments[0].speaker == "SPEAKER_01"
    assert removed_ids == [existing.id]
    assert new.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_lowercase_continuation_only_merges_same_speaker():
    a = _segment("hello", speaker="SPEAKER_00", start=0.0, end=1.0)
    b = _segment("world", speaker="SPEAKER_01", start=1.2, end=2.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, _, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_backward_merge_first_sentence_from_next_segment():
    a = _segment(
        "There are so many versions of trying to get a similar idea of digital objects in physical space",
        speaker="SPEAKER_02",
        start=0.0,
        end=2.0,
    )
    b = _segment("move. Mhmm.", speaker="SPEAKER_01", start=2.0, end=2.5)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert segments[0].speaker == "SPEAKER_02"
    assert segments[0].text.endswith("space move.")
    assert segments[1].speaker == "SPEAKER_01"
    assert segments[1].text == "Mhmm."
    assert len(updated_segments) == 2
    assert updated_segments[0].speaker == "SPEAKER_02"
    assert updated_segments[1].speaker == "SPEAKER_01"
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_backward_merge_preserves_next_segment_when_more_sentences_remain():
    a = _segment("This is an incomplete thought", speaker="SPEAKER_00", start=0.0, end=2.0)
    b = _segment("continued here. Another sentence stays.", speaker="SPEAKER_01", start=2.0, end=4.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert segments[0].speaker == "SPEAKER_00"
    assert segments[0].text.endswith("continued here.")
    assert segments[1].speaker == "SPEAKER_01"
    assert segments[1].text == "Another sentence stays."
    assert len(updated_segments) == 2
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_backward_merge_single_lowercase_sentence_from_next_segment():
    a = _segment(
        "Maybe it's a 20 degree or 30 degree field of view and we read faster than we can",
        speaker="SPEAKER_01",
        start=0.0,
        end=2.0,
    )
    b = _segment("listen.", speaker="SPEAKER_02", start=2.0, end=2.2)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 1
    assert segments[0].speaker == "SPEAKER_01"
    assert segments[0].text.endswith("listen.")
    assert len(updated_segments) == 1
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_merge_lowercase_continuation_same_speaker():
    a = _segment("Hello", speaker="SPEAKER_00", start=0.0, end=1.0)
    b = _segment("world", speaker="SPEAKER_00", start=1.1, end=2.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 1
    assert segments[0].text == "Hello world"
    assert len(updated_segments) == 1
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_backward_merge_lowercase_phrase_between_same_speaker_segments():
    a = _segment(
        "Then I don't at the same time, we only have so many hours in the day, so people need to prioritize what "
        "they're gonna learn. It may be that, okay, a world with perfect translation, which the way, we basically "
        "just announced on the Ray Ban Meta is that now you're gonna be able to",
        speaker="SPEAKER_1",
        start=0.0,
        end=2.0,
    )
    b = _segment("just, like, go to different countries", speaker="SPEAKER_2", start=2.1, end=2.5)
    c = _segment(
        "we're starting out. We're we're starting out with just a few languages, but we'll roll it out to more.",
        speaker="SPEAKER_1",
        start=2.5,
        end=3.5,
    )
    input_concat = _concat_texts([a.text, b.text, c.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b, c])

    assert len(segments) == 1
    assert segments[0].speaker == "SPEAKER_1"
    assert "able to just, like, go to different countries" in segments[0].text
    assert len(updated_segments) == 1
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert c.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_backward_merge_lowercase_phrase_at_end_of_speaker_segment():
    a = _segment(
        "Like, for example, you mentioned automatic real time translation. Mhmm. Like, basically, the Star Trek "
        "translator. Yeah. Universal translator. Think they were",
        speaker="SPEAKER_3",
        start=0.0,
        end=2.0,
    )
    b = _segment("pretty much", speaker="SPEAKER_1", start=2.0, end=2.5)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 1
    assert segments[0].speaker == "SPEAKER_3"
    assert segments[0].text.endswith("pretty much")
    assert len(updated_segments) == 1
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_updated_segments_returned_for_new_non_merge():
    a = _segment("Hello.", speaker="SPEAKER_00", start=0.0, end=1.0)
    b = _segment("Hi.", speaker="SPEAKER_01", start=1.1, end=2.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert len(updated_segments) == 2
    assert updated_segments[0].text == "Hello."
    assert updated_segments[1].text == "Hi."
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_delta_seconds_shifts_timestamps():
    a = _segment("Hello.", speaker="SPEAKER_00", start=1.0, end=2.0)
    input_concat = _concat_texts([a.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a], delta_seconds=5)

    assert len(segments) == 1
    assert segments[0].start == pytest.approx(6.0)
    assert segments[0].end == pytest.approx(7.0)
    assert len(updated_segments) == 1
    assert removed_ids == []
    assert a.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_no_merge_when_stt_provider_differs():
    a = _segment("Hello", speaker="SPEAKER_00", start=0.0, end=1.0)
    b = _segment("world.", speaker="SPEAKER_00", start=1.1, end=2.0)
    a.stt_provider = "provider_a"
    b.stt_provider = "provider_b"
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 2
    assert segments[0].text == "Hello"
    assert segments[1].text == "world."
    assert len(updated_segments) == 2
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_punctuation_cleanup_normalizes_spacing():
    a = _segment("Hello , world .", speaker="SPEAKER_00", start=0.0, end=1.0)
    input_concat = _concat_texts([a.text])
    expected_concat = _normalize_punctuation(input_concat)

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a])

    assert len(segments) == 1
    assert segments[0].text == "Hello, world."
    assert len(updated_segments) == 1
    assert removed_ids == []
    assert a.id not in removed_ids
    assert _concat_segments(segments) == expected_concat


def test_empty_text_segment_does_not_break_concat():
    a = _segment("Hello", speaker="SPEAKER_00", start=0.0, end=1.0)
    b = _segment("   ", speaker="SPEAKER_00", start=1.1, end=2.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 1
    assert segments[0].text == "Hello"
    assert len(updated_segments) == 1
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat


def test_non_latin_text_merges_same_speaker():
    a = _segment("こんにちは", speaker="SPEAKER_00", start=0.0, end=1.0)
    b = _segment("世界。", speaker="SPEAKER_00", start=1.1, end=2.0)
    input_concat = _concat_texts([a.text, b.text])

    segments, updated_segments, removed_ids = TranscriptSegment.combine_segments([], [a, b])

    assert len(segments) == 1
    assert segments[0].text == "こんにちは 世界。"
    assert len(updated_segments) == 1
    assert removed_ids == []
    assert a.id not in removed_ids
    assert b.id not in removed_ids
    assert _concat_segments(segments) == input_concat
