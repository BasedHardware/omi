from utils.stt.pre_recorded import _merge_segments


def test_merge_segments_max_size():
    words = [{"text": "word", "start": i, "end": i + 0.5, "speaker": "SPEAKER_00"} for i in range(100)]
    segments = _merge_segments(words, skip_n_seconds=0, user_speaker_id=None)
    assert len(segments) == 4
    assert [len(segment["text"].split()) for segment in segments] == [30, 30, 30, 10]
    for s in segments:
        assert s["end"] - s["start"] <= 30


def test_merge_segments_splits_long_provider_entry():
    words = [
        {
            "text": "one two three four five six seven eight nine ten eleven twelve",
            "start": 0,
            "end": 75,
            "speaker": "SPEAKER_00",
        }
    ]

    segments = _merge_segments(words, skip_n_seconds=0, user_speaker_id=None)

    assert [(segment["start"], segment["end"]) for segment in segments] == [(0, 25), (25, 50), (50, 75)]
    assert [segment["text"] for segment in segments] == [
        "one two three four",
        "five six seven eight",
        "nine ten eleven twelve",
    ]
    assert " ".join(segment["text"] for segment in segments) == words[0]["text"]


def test_split_long_entry_never_emits_empty_text():
    words = [{"text": "monologue", "start": 0, "end": 61, "speaker": "SPEAKER_00"}]

    segments = _merge_segments(words, skip_n_seconds=0, user_speaker_id=None)

    assert [segment["text"] for segment in segments] == ["monologue"]
    assert all(segment["text"].strip() for segment in segments)


def test_split_long_entry_allocates_text_proportionally_to_slice_duration():
    words = [{"text": "a b c d e f", "start": 0, "end": 61, "speaker": "SPEAKER_00"}]

    segments = _merge_segments(words, skip_n_seconds=0, user_speaker_id=None)

    durations = [segment["end"] - segment["start"] for segment in segments]
    counts = [len(segment["text"].split()) for segment in segments]
    assert counts == [2, 2, 2]
    assert max(durations) - min(durations) < 1e-6
    assert max(durations) <= 30


def test_entry_at_cap_is_returned_unchanged():
    entry = {"text": "a b c", "start": 0, "end": 30, "speaker": "SPEAKER_00"}

    segments = _merge_segments([dict(entry)], skip_n_seconds=0, user_speaker_id=None)

    assert len(segments) == 1
    assert (segments[0]["start"], segments[0]["end"], segments[0]["text"]) == (0, 30, "a b c")
