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

    assert [(segment["start"], segment["end"]) for segment in segments] == [(0, 30), (30, 60), (60, 75)]
    assert [segment["text"] for segment in segments] == [
        "one two three four",
        "five six seven eight",
        "nine ten eleven twelve",
    ]
    assert " ".join(segment["text"] for segment in segments) == words[0]["text"]
