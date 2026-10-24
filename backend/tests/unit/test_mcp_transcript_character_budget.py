"""The transcript character budget bounds every text field the reader returns."""

from utils.mcp_server.helpers import bounded_transcript_segments


def test_character_budget_counts_original_text():
    segments = [
        {"id": "s1", "text": "hello", "original_text": "a" * 20},
        {"id": "s2", "text": "world", "original_text": "b" * 20},
    ]

    bounded, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=10)

    assert truncated is True
    assert len(bounded) == 1
    assert bounded[0]["text"] == "hello"
    assert bounded[0]["original_text"] == "a" * 5
    assert len(bounded[0]["text"]) + len(bounded[0]["original_text"]) == 10


def test_character_budget_clipping_original_text_reports_truncation():
    bounded, truncated = bounded_transcript_segments(
        [{"id": "s1", "text": "hello", "original_text": "a" * 20}],
        max_segments=10,
        max_chars=5,
    )

    assert truncated is True
    assert bounded[0]["text"] == "hello"
    assert bounded[0]["original_text"] == ""


def test_character_budget_multi_segment_boundary_accounting():
    # Segment 1 uses 3 + 2 = 5 chars; remaining budget is 5.
    # Segment 2 uses 4 chars for text; remaining 1 char clips original_text to 1 char.
    segments = [
        {"id": "s1", "text": "abc", "original_text": "ab"},
        {"id": "s2", "text": "1234", "original_text": "12345"},
    ]

    bounded, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=10)

    assert truncated is True
    assert len(bounded) == 2
    assert bounded[0]["text"] == "abc"
    assert bounded[0]["original_text"] == "ab"
    assert bounded[1]["text"] == "1234"
    assert bounded[1]["original_text"] == "1"
    total_chars = sum(len(s["text"]) + len(s.get("original_text") or "") for s in bounded)
    assert total_chars == 10


def test_character_budget_none_original_text_preserved():
    segments = [
        {"id": "s1", "text": "test", "original_text": None},
    ]

    bounded, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=10)

    assert truncated is False
    assert len(bounded) == 1
    assert bounded[0]["text"] == "test"
    assert bounded[0]["original_text"] is None


def test_character_budget_without_original_text_key():
    segments = [
        {"id": "s1", "text": "hello world"},
        {"id": "s2", "text": "foo bar"},
    ]

    bounded, truncated = bounded_transcript_segments(segments, max_segments=10, max_chars=100)

    assert truncated is False
    assert len(bounded) == 2
    assert bounded[0]["text"] == "hello world"
    assert "original_text" not in bounded[0]
    assert bounded[1]["text"] == "foo bar"
    assert "original_text" not in bounded[1]
