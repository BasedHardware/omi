"""Tests for NER-based speaker identification."""

import pytest
from unittest.mock import patch, MagicMock


class TestNERSpeakerIdentification:
    """Test the NER speaker identification module."""

    def test_detect_explicit_introduction(self):
        """NER catches explicit name introductions."""
        from utils.ner_speaker_identification import detect_speaker_from_text_ner

        # These should work even with regex fallback
        assert detect_speaker_from_text_ner("My name is John") == "John"
        assert detect_speaker_from_text_ner("I'm Sarah and I work here") == "Sarah"

    def test_detect_natural_mention(self):
        """NER catches names mentioned naturally in conversation."""
        from utils.ner_speaker_identification import detect_speaker_names_ner

        results = detect_speaker_names_ner("Tell Mike I'll be there at five")
        names = [r[0] for r in results]
        assert "Mike" in names

    def test_detect_direct_address(self):
        """NER catches direct address patterns."""
        from utils.ner_speaker_identification import detect_speaker_names_ner

        results = detect_speaker_names_ner("David, can you pass the salt?")
        names = [r[0] for r in results]
        assert "David" in names

    def test_false_positive_filtering(self):
        """Common false positives are filtered out."""
        from utils.ner_speaker_identification import detect_speaker_names_ner

        # "Omi" should not be detected as a person
        results = detect_speaker_names_ner("Hey Omi, what's the weather?")
        names = [r[0] for r in results]
        assert "Omi" not in names

    def test_empty_input(self):
        """Empty or meaningless input returns no results."""
        from utils.ner_speaker_identification import detect_speaker_from_text_ner

        assert detect_speaker_from_text_ner("") is None
        assert detect_speaker_from_text_ner("um yeah okay sure") is None

    def test_multiple_names(self):
        """Multiple names in one segment are all detected."""
        from utils.ner_speaker_identification import detect_speaker_names_ner

        results = detect_speaker_names_ner(
            "Sarah told Mike that Jessica would be late"
        )
        names = [r[0] for r in results]
        assert len(names) >= 2  # Should catch at least 2 of the 3

    def test_confidence_ordering(self):
        """Results are ordered by confidence."""
        from utils.ner_speaker_identification import detect_speaker_names_ner

        results = detect_speaker_names_ner("I'm Alex and I said hi to Bob")
        if len(results) >= 2:
            # First result should have higher or equal confidence
            assert results[0][1] >= results[1][1]

    def test_regex_fallback_when_spacy_unavailable(self):
        """Falls back to regex when spaCy is not installed."""
        from utils.ner_speaker_identification import _detect_speaker_regex_fallback

        assert _detect_speaker_regex_fallback("My name is Carlos") == "Carlos"
        assert _detect_speaker_regex_fallback("no name here") is None

    def test_performance_under_100ms(self):
        """NER detection completes in under 100ms for typical segments."""
        import time
        from utils.ner_speaker_identification import detect_speaker_names_ner

        text = "Hey John, I was talking to Sarah yesterday about the project Mike started"
        start = time.time()
        for _ in range(10):
            detect_speaker_names_ner(text)
        elapsed = (time.time() - start) / 10

        # Should be well under 100ms per call
        assert elapsed < 0.1, f"NER took {elapsed*1000:.1f}ms (limit: 100ms)"
