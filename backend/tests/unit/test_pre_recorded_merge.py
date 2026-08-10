from utils.stt.pre_recorded import _merge_segments

def test_merge_segments_max_size():
    words = [
        {"text": "word", "start": i, "end": i + 0.5, "speaker": "SPEAKER_00"} for i in range(100)
    ]
    segments = _merge_segments(words, skip_n_seconds=0, user_speaker_id=None)
    assert len(segments) > 1, f"Expected more than 1 segment, got {len(segments)}"
    for s in segments:
        assert s["end"] - s["start"] < 30, f"Segment duration exceeded 30s: {s['end'] - s['start']}"
