from utils.mcp_server.helpers import bounded_transcript_segments


def test_bounded_transcript_segments_without_original_text():
    segments = [
        {"id": "1", "text": "hello world"},
        {"id": "2", "text": "foo bar"},
    ]
    result, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=100)
    assert len(result) == 2
    assert truncated is False
    assert result[0]["text"] == "hello world"
    assert result[1]["text"] == "foo bar"


def test_bounded_transcript_segments_original_text_within_budget():
    segments = [
        {"id": "1", "text": "hello", "original_text": "helo"},
    ]
    result, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=20)
    assert len(result) == 1
    assert truncated is False
    assert result[0]["text"] == "hello"
    assert result[0]["original_text"] == "helo"


def test_bounded_transcript_segments_original_text_clipped_and_truncated():
    # Issue #22806 reproducer: text (5) + original_text (20), max_chars: 10
    segments = [
        {"id": "1", "text": "hello", "original_text": "01234567890123456789"},
    ]
    result, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=10)
    assert len(result) == 1
    assert truncated is True
    assert result[0]["text"] == "hello"
    assert result[0]["original_text"] == "01234"
    total_chars = len(result[0]["text"]) + len(result[0]["original_text"])
    assert total_chars == 10


def test_bounded_transcript_segments_text_consumes_entire_budget():
    segments = [
        {"id": "1", "text": "0123456789", "original_text": "corrected version"},
    ]
    result, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=10)
    assert len(result) == 1
    assert truncated is True
    assert result[0]["text"] == "0123456789"
    assert result[0]["original_text"] == ""


def test_bounded_transcript_segments_multi_segment_budget_accounting():
    segments = [
        {"id": "1", "text": "abc", "original_text": "ab"},     # 3 + 2 = 5 chars
        {"id": "2", "text": "1234", "original_text": "12345"}, # 4 + 5 = 9 chars
    ]
    # max_chars = 10: segment 1 uses 5. Segment 2 has 5 left -> text uses 4, orig uses 1.
    result, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=10)
    assert len(result) == 2
    assert truncated is True
    assert result[0]["text"] == "abc"
    assert result[0]["original_text"] == "ab"
    assert result[1]["text"] == "1234"
    assert result[1]["original_text"] == "1"
    total_chars = sum(len(s["text"]) + len(s.get("original_text") or "") for s in result)
    assert total_chars == 10


def test_bounded_transcript_segments_none_original_text_handled():
    segments = [
        {"id": "1", "text": "test", "original_text": None},
    ]
    result, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=10)
    assert len(result) == 1
    assert truncated is False
    assert result[0]["text"] == "test"
    assert result[0]["original_text"] is None
