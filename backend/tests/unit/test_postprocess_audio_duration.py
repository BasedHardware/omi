from types import SimpleNamespace

from utils.conversations.postprocess_conversation import _minimum_audio_duration


def test_transcript_based_minimum_duration_never_drops_below_ten_seconds():
    segments = [SimpleNamespace(start=0.0, end=15.0)]

    assert _minimum_audio_duration(segments) == 10.0


def test_transcript_based_minimum_duration_allows_the_transcript_padding_window():
    segments = [SimpleNamespace(start=0.0, end=25.0)]

    assert _minimum_audio_duration(segments) == 15.0
