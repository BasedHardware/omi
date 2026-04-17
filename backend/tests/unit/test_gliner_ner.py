"""Unit tests for GLiNER NER integration in speaker identification.

Tests the _clean_person_name() function for title/prefix filtering
and detect_speaker_from_text() with GLiNER + regex fallback.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest
import asyncio

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
sys.modules.setdefault("database._client", MagicMock())
sys.modules.setdefault("database.users", MagicMock())
sys.modules.setdefault("database.conversations", MagicMock())
sys.modules.setdefault("utils.other.storage", MagicMock())
sys.modules.setdefault("utils.stt.pre_recorded", MagicMock())
sys.modules.setdefault("utils.speaker_sample", MagicMock())
sys.modules.setdefault("utils.speaker_sample_migration", MagicMock())
sys.modules.setdefault("utils.stt.speaker_embedding", MagicMock())

from utils.speaker_identification import (
    detect_speaker_from_text,
    batch_detect_speakers_from_texts,
    _clean_person_name,
)


class TestCleanPersonName:
    """Tests for title and prefix filtering in _clean_person_name()."""

    def test_filters_dr_title(self):
        """Dr. prefix should be filtered to get actual name."""
        assert _clean_person_name("Dr. Emily Chen") == "Emily"

    def test_filters_dr_title_without_period(self):
        """Dr without period should also be filtered."""
        assert _clean_person_name("Dr Emily") == "Emily"

    def test_filters_mr_title(self):
        """Mr. prefix should be filtered."""
        assert _clean_person_name("Mr. Robert Williams") == "Robert"

    def test_filters_mrs_title(self):
        """Mrs. prefix should be filtered."""
        assert _clean_person_name("Mrs. Sarah") == "Sarah"

    def test_filters_ms_title(self):
        """Ms. prefix should be filtered."""
        assert _clean_person_name("Ms. Jennifer") == "Jennifer"

    def test_filters_prof_title(self):
        """Prof. prefix should be filtered."""
        assert _clean_person_name("Prof. John Davis") == "John"

    def test_filters_rev_title(self):
        """Rev. prefix should be filtered."""
        assert _clean_person_name("Rev. Michael") == "Michael"

    def test_filters_hon_title(self):
        """Hon. prefix should be filtered."""
        assert _clean_person_name("Hon. Patricia") == "Patricia"

    def test_filters_capt_title(self):
        """Capt. prefix should be filtered."""
        assert _clean_person_name("Capt. James") == "James"

    def test_filters_gen_title(self):
        """Gen. prefix should be filtered."""
        assert _clean_person_name("Gen. Washington") == "Washington"

    def test_filters_sr_title(self):
        """Sr. prefix should be filtered."""
        assert _clean_person_name("Sr. Martinez") == "Martinez"

    def test_filters_jr_title(self):
        """Jr. prefix should be filtered."""
        assert _clean_person_name("Jr. Thompson") == "Thompson"

    def test_keeps_regular_names(self):
        """Regular names should be returned unchanged."""
        assert _clean_person_name("John") == "John"
        assert _clean_person_name("Sarah") == "Sarah"
        assert _clean_person_name("Michael") == "Michael"

    def test_keeps_multipart_first_names(self):
        """First word of multi-word names should be returned."""
        assert _clean_person_name("John Smith") == "John"
        assert _clean_person_name("Vanessa Brown") == "Vanessa"

    def test_filters_single_letter(self):
        """Single letters should return None."""
        assert _clean_person_name("J") is None
        assert _clean_person_name("M") is None

    def test_handles_empty_string(self):
        """Empty strings should return None."""
        assert _clean_person_name("") is None
        assert _clean_person_name("   ") is None

    def test_handles_only_title(self):
        """String with only title should return None."""
        assert _clean_person_name("Dr.") is None
        assert _clean_person_name("Mr.") is None

    def test_capitalizes_result(self):
        """Result should be capitalized."""
        assert _clean_person_name("john") == "John"
        assert _clean_person_name("SARAH") == "Sarah"


class TestDetectSpeakerFromText:
    """Tests for detect_speaker_from_text() with GLiNER NER and regex fallback."""

    def test_detects_name_with_explicit_introduction(self):
        """Simple 'I am X' pattern should be detected."""
        result = detect_speaker_from_text("I am John")
        assert result == "John"

    def test_detects_name_with_implicit_introduction(self):
        """'This is X' pattern should be detected via GLiNER."""
        result = detect_speaker_from_text("This is John calling")
        assert result == "John"

    def test_filters_title_in_full_sentence(self):
        """Titles in full sentences should be filtered."""
        result = detect_speaker_from_text("This is Dr. Emily Chen")
        assert result == "Emily"

    def test_filters_mr_title_in_sentence(self):
        """Mr. title in sentence should be filtered."""
        result = detect_speaker_from_text("Hi, Mr. Robert Williams here")
        assert result == "Robert"

    def test_filters_prof_title_in_sentence(self):
        """Prof. title in sentence should be filtered."""
        result = detect_speaker_from_text("Prof. John Davis here")
        assert result == "John"

    def test_detects_name_with_apostrophe(self):
        """Names with apostrophe should work."""
        result = detect_speaker_from_text("I'm Sarah")
        assert result == "Sarah"

    def test_detects_name_with_my_name_is(self):
        """'My name is X' pattern should work."""
        result = detect_speaker_from_text("My name is Mike")
        assert result == "Mike"

    def test_detects_name_speaking_pattern(self):
        """'X speaking' pattern should work."""
        result = detect_speaker_from_text("David speaking")
        assert result == "David"

    def test_detects_name_here_pattern(self):
        """'X here' pattern should work."""
        result = detect_speaker_from_text("Lisa here")
        assert result == "Lisa"

    def test_returns_none_for_no_name(self):
        """Sentences without names should return None."""
        result = detect_speaker_from_text("Just calling to say hi")
        assert result is None

    def test_returns_none_for_empty(self):
        """Empty input should return None."""
        result = detect_speaker_from_text("")
        assert result is None

    def test_returns_none_for_short_text(self):
        """Very short text should return None."""
        result = detect_speaker_from_text("Hi")
        assert result is None

    def test_handles_multilingual_names(self):
        """Various name patterns should work."""
        result = detect_speaker_from_text("Bonjour, je suis Marie")
        assert result is None or isinstance(result, str)

    def test_handles_complex_name(self):
        """Complex names like 'John Smith here' should return first name."""
        result = detect_speaker_from_text("Hello, John Smith here")
        assert result == "John"


class TestBatchDetectSpeakersFromTexts:
    """Tests for async batch_detect_speakers_from_texts()."""

    def test_batch_processes_multiple_texts(self):
        """Batch should process multiple texts correctly."""
        texts = [
            "This is John calling",
            "Hi, I'm Sarah",
            "My name is Mike",
        ]
        results = asyncio.run(batch_detect_speakers_from_texts(texts))

        assert len(results) == 3
        assert results[0] == "John"
        assert results[1] == "Sarah"
        assert results[2] == "Mike"

    def test_batch_handles_empty_texts(self):
        """Batch should handle empty texts."""
        texts = ["This is John", "", "I'm Sarah"]
        results = asyncio.run(batch_detect_speakers_from_texts(texts))

        assert len(results) == 3
        assert results[0] == "John"
        assert results[1] is None
        assert results[2] == "Sarah"

    def test_batch_handles_no_names(self):
        """Batch should handle texts with no names."""
        texts = [
            "Just calling to say hi",
            "How are you doing",
        ]
        results = asyncio.run(batch_detect_speakers_from_texts(texts))

        assert len(results) == 2
        assert results[0] is None
        assert results[1] is None

    def test_batch_filters_titles(self):
        """Batch should filter titles correctly."""
        texts = [
            "This is Dr. Emily Chen",
            "Mr. Robert speaking",
        ]
        results = asyncio.run(batch_detect_speakers_from_texts(texts))

        assert len(results) == 2
        assert results[0] == "Emily"
        assert results[1] == "Robert"

    def test_batch_mixed_results(self):
        """Batch should handle mix of results."""
        texts = [
            "This is John",
            "Just talking",
            "I'm Sarah",
            "",
            "Hey, it's Mike",
        ]
        results = asyncio.run(batch_detect_speakers_from_texts(texts))

        assert len(results) == 5
        assert results[0] == "John"
        assert results[1] is None
        assert results[2] == "Sarah"
        assert results[3] is None
        assert results[4] == "Mike"
