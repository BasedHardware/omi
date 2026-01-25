"""
Unit tests for compute_text_containment function.
Tests character trigram containment across multiple languages.
"""

from utils.text_utils import compute_text_containment


class TestComputeTextContainment:
    """Tests for the compute_text_containment function."""

    def test_transcript_fully_contained(self):
        transcript = "hello world nice day"
        expected = "greetings hello world nice day everyone"
        assert compute_text_containment(transcript, expected) == 1.0

    def test_transcript_not_contained(self):
        transcript = "hello world nice day"
        expected = "greetings hello world pleasant evening"
        containment = compute_text_containment(transcript, expected)
        assert containment < 0.9

    def test_empty_transcript(self):
        assert compute_text_containment("", "hello") == 0.0

    def test_short_transcript_contained(self):
        assert compute_text_containment("hi", "oh hi there") == 1.0

    def test_short_transcript_not_contained(self):
        assert compute_text_containment("hi", "hello there") == 0.0

    def test_case_and_whitespace_normalization(self):
        transcript = "Hello   World"
        expected = "greetings hello world everyone"
        assert compute_text_containment(transcript, expected) == 1.0

    def test_chinese_contained(self):
        transcript = "你好世界"
        expected = "今天你好世界朋友"
        assert compute_text_containment(transcript, expected) == 1.0

    def test_thai_contained(self):
        transcript = "สวัสดีครับ"
        expected = "วันนี้สวัสดีครับเพื่อนๆ"
        assert compute_text_containment(transcript, expected) == 1.0

    def test_expected_empty_returns_zero(self):
        assert compute_text_containment("hello", "") == 0.0

    def test_trigram_length_boundary_contained(self):
        assert compute_text_containment("hey", "oh hey there") == 1.0

    def test_trigram_length_boundary_not_contained(self):
        assert compute_text_containment("hey", "oh he there") == 0.0
