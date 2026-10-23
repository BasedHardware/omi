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
