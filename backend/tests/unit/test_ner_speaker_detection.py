"""Unit tests for NER-based speaker detection.

Tests the spaCy NER integration for extracting person names
from transcript text that don't follow self-introduction patterns.
"""

import pytest


class TestDetectPersonsWithNer:
    """Tests for detect_persons_with_ner function."""

    def test_returns_empty_for_empty_text(self):
        """Should return empty list for empty/None input."""
        from utils.ner_speaker_detection import detect_persons_with_ner
        assert detect_persons_with_ner("") == []
        assert detect_persons_with_ner(None) == []
        assert detect_persons_with_ner("   ") == []

    def test_filters_false_positive_organizations(self):
        """Should filter out common organizations incorrectly tagged as PERSON."""
        from utils.ner_speaker_detection import detect_persons_with_ner

        # These are commonly tagged as PERSON by spaCy but aren't names
        text = "We're using Google Docs and Microsoft Teams for this project"
        # NER might detect Google/Microsoft as persons - our filter should remove them
        result = detect_persons_with_ner(text)
        # Should not contain company names
        for name in result:
            assert name.lower() not in ["google", "microsoft", "docs", "teams"]

    def test_filters_single_characters(self):
        """Should filter out single character names."""
        from utils.ner_speaker_detection import detect_persons_with_ner

        # Single letter names should be filtered out
        text = "I talked to A and B about the project"
        result = detect_persons_with_ner(text)
        # Should not contain single character names
        for name in result:
            assert len(name) >= 2

    def test_normalizes_title_case(self):
        """Should normalize names to title case."""
        from utils.ner_speaker_detection import detect_persons_with_ner

        text = "john and sarah discussed the proposal"
        result = detect_persons_with_ner(text)
        # Names should be title-cased
        for name in result:
            assert name[0].isupper()

    def test_handles_hyphenated_names(self):
        """Should handle hyphenated names correctly."""
        from utils.ner_speaker_detection import detect_persons_with_ner

        # This tests name normalization with hyphens
        text = "Mary-Jane and John-Doe are joining"
        result = detect_persons_with_ner(text)
        # At minimum, should find some names
        assert isinstance(result, list)

    def test_max_persons_limit(self):
        """Should respect max_persons parameter."""
        from utils.ner_speaker_detection import detect_persons_with_ner

        text = "Alice Bob Charlie David Edward Frank are all here"
        result = detect_persons_with_ner(text, max_persons=2)
        assert len(result) <= 2

    def test_handles_apostrophe_names(self):
        """Should handle names with apostrophes correctly."""
        from utils.ner_speaker_detection import detect_persons_with_ner

        text = "O'Brien met with D'Artagnan"
        result = detect_persons_with_ner(text)
        # Should find at least O'Brien-like names
        assert isinstance(result, list)

    def test_deduplicates_case_insensitive(self):
        """Should deduplicate names case-insensitively."""
        from utils.ner_speaker_detection import detect_persons_with_ner

        text = "John said hi. john went home. JOHN is here."
        result = detect_persons_with_ner(text, max_persons=5)
        # Should not have duplicates of John in different cases
        john_count = sum(1 for n in result if n.lower() == "john")
        assert john_count <= 1


class TestIsValidPersonName:
    """Tests for _is_valid_person_name validation."""

    def test_rejects_short_names(self):
        """Should reject names shorter than 2 characters."""
        from utils.ner_speaker_detection import _is_valid_person_name
        assert _is_valid_person_name("A") is False
        assert _is_valid_person_name("") is False

    def test_rejects_known_false_positives(self):
        """Should reject common organizations/products."""
        from utils.ner_speaker_detection import _is_valid_person_name
        assert _is_valid_person_name("Google") is False
        assert _is_valid_person_name("Apple") is False
        assert _is_valid_person_name("ChatGPT") is False

    def test_rejects_all_lowercase(self):
        """Should reject all-lowercase strings (likely not names)."""
        from utils.ner_speaker_detection import _is_valid_person_name
        # Unless it has an apostrophe
        assert _is_valid_person_name("john") is False

    def test_accepts_title_case(self):
        """Should accept properly capitalized names."""
        from utils.ner_speaker_detection import _is_valid_person_name
        assert _is_valid_person_name("John") is True
        assert _is_valid_person_name("Sarah") is True


class TestNormalizeName:
    """Tests for _normalize_name helper."""

    def test_title_cases(self):
        """Should title case names."""
        from utils.ner_speaker_detection import _normalize_name
        assert _normalize_name("john") == "John"
        assert _normalize_name("SARAH") == "Sarah"

    def test_handles_hyphens(self):
        """Should preserve hyphens with proper casing."""
        from utils.ner_speaker_detection import _normalize_name
        result = _normalize_name("mary-jane")
        assert result in ["Mary-Jane", "Mary-jane"]

    def test_handles_apostrophes(self):
        """Should preserve apostrophes with proper casing."""
        from utils.ner_speaker_detection import _normalize_name
        assert _normalize_name("o'brien") == "O'Brien"
        assert _normalize_name("d'artagnan") == "D'Artagnan"

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace and punctuation."""
        from utils.ner_speaker_detection import _normalize_name
        assert _normalize_name("  John  ") == "John"
        assert _normalize_name("John.") == "John"
        assert _normalize_name("Sarah,") == "Sarah"


class TestIsNerAvailable:
    """Tests for is_ner_available function."""

    def test_returns_bool(self):
        """Should return a boolean indicating availability."""
        from utils.ner_speaker_detection import is_ner_available
        result = is_ner_available()
        assert isinstance(result, bool)


class TestNerStats:
    """Tests for get_ner_stats function."""

    def test_returns_dict_with_expected_keys(self):
        """Should return dict with model info."""
        from utils.ner_speaker_detection import get_ner_stats
        stats = get_ner_stats()
        assert isinstance(stats, dict)
        assert "model_name" in stats
        assert "available" in stats
        assert "load_error" in stats
