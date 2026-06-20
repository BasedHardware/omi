"""Edge-case tests for DD-008 translation dedup pipeline.

Tests split_into_sentences abbreviation handling in isolation (no heavy deps)
plus structural checks on translation_coordinator.py and translation.py source.

Covers bot-identified correctness gaps:
- Abbreviation-aware sentence splitting (P2) — U.S., 3.14, e.g., etc.
- Full-text cache consulted before sentence-level split (P2)
- No-op path version bump + batch buffer invalidation (P1)
- Memory cache not poisoned by failed translations (P1)
- Sync Redis offloaded to run_blocking in async observe() (P2)
"""

from __future__ import annotations

import importlib
import os
import sys
import types
import unittest

# ---------------------------------------------------------------------------
# Import the real splitter under a fake Google Translate client.
# ---------------------------------------------------------------------------
# The sentence splitter is pure, but utils.translation creates the Google client
# at import time. Keep these tests focused on the splitter by stubbing that
# client before importing the production module. This avoids the previous test
# smell where the test copied the splitter implementation and could pass while
# production code regressed.
_fake_translate_v3 = types.ModuleType('google.cloud.translate_v3')
setattr(_fake_translate_v3, 'TranslationServiceClient', lambda *args, **kwargs: object())
try:
    _google_cloud = importlib.import_module('google.cloud')
except Exception:
    _google = types.ModuleType('google')
    _google_cloud = types.ModuleType('google.cloud')
    setattr(_google, 'cloud', _google_cloud)
    sys.modules.setdefault('google', _google)
    sys.modules.setdefault('google.cloud', _google_cloud)
setattr(_google_cloud, 'translate_v3', _fake_translate_v3)
sys.modules['google.cloud.translate_v3'] = _fake_translate_v3

from utils.translation import split_into_sentences  # noqa: E402

# ===========================================================================
# TESTS — Abbreviation Splitting (P2 from Codex bot review)
# ===========================================================================


class TestAbbreviationSplitting(unittest.TestCase):
    """Verify split_into_sentences doesn't break on common abbreviations.

    These are the specific cases flagged by the Codex bot reviewer on PR #7954.
    The algorithm uses placeholder protection for internal periods + post-split
    merge heuristics for false sentence boundaries at abbreviation tails.
    """

    # ---- Bot-reported cases (MUST pass) ----

    def test_us_abbreviation_not_split(self):
        """'I live in the U.S. now.' must not become ['I live in the U.', 'S.', 'now.']"""
        result = split_into_sentences("I live in the U.S. now.")
        self.assertEqual(len(result), 1, f"Expected 1 sentence, got {result}: {repr(result)}")
        self.assertIn("U.S.", result[0])

    def test_version_number_not_split(self):
        """'Version 3.11 is installed.' must not break at the decimal point."""
        result = split_into_sentences("Version 3.11 is installed.")
        self.assertEqual(len(result), 1, f"Expected 1 sentence, got {result}: {repr(result)}")
        self.assertIn("3.11", result[0])

    # ---- Related abbreviation cases ----

    def test_uk_abbreviation_not_split(self):
        result = split_into_sentences("She is from the U.K. She likes tea.")
        self.assertEqual(len(result), 2, f"Expected 2 sentences, got {result}: {repr(result)}")
        self.assertIn("U.K.", result[0])

    def test_acronym_sentence_enders_split_before_capitalized_next_sentence(self):
        """Generalized regression for the latest review: acronym at true boundary."""
        countries = ("U.S.", "U.K.", "E.U.")
        next_sentences = ("She likes tea.", "They agreed.", "Markets opened higher.")
        for acronym in countries:
            for following in next_sentences:
                with self.subTest(acronym=acronym, following=following):
                    text = f"She is from the {acronym} {following}"
                    self.assertEqual(
                        split_into_sentences(text),
                        [f"She is from the {acronym}", following],
                    )

    def test_acronym_fragments_stay_joined_before_lowercase_continuation(self):
        """The boundary guard should not regress continuation cases like U.S. policy."""
        cases = (
            "I live in the U.S. now.",
            "The U.K. policy changed.",
            "The E.U. market opened.",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(split_into_sentences(text), [text])

    def test_generated_short_sentences_do_not_merge_with_following_capitalized_sentence(self):
        """Fuzz-ish matrix: short utterances are common STT units, not abbreviations."""
        starters = ("Hi.", "OK.", "Sí.", "No.", "Yes.", "Go.")
        followers = ("Thanks.", "There it is.", "We agree.", "Another sentence.")
        for first in starters:
            for second in followers:
                with self.subTest(first=first, second=second):
                    self.assertEqual(split_into_sentences(f"{first} {second}"), [first, second])

    def test_decimal_number_not_split(self):
        result = split_into_sentences("The value is 3.14159. It is precise.")
        self.assertEqual(len(result), 2, f"Expected 2 sentences, got {result}: {repr(result)}")
        self.assertIn("3.14159", result[0])

    def test_dr_title_followed_by_name(self):
        """'Dr. Smith arrived. He was late.' → 2 sentences."""
        result = split_into_sentences("Dr. Smith arrived. He was late.")
        self.assertEqual(len(result), 2, f"Expected 2 sentences, got {result}: {repr(result)}")

    def test_etc_at_end_of_clause(self):
        result = split_into_sentences("We need apples, oranges, etc. for the pie.")
        self.assertEqual(len(result), 1, f"Expected 1 sentence, got {result}: {repr(result)}")
        self.assertIn("etc.", result[0])

    def test_eg_ie_not_split(self):
        result = split_into_sentences("Use fruits e.g. apples. It works well.")
        self.assertEqual(len(result), 2, f"Expected 2 sentences, got {result}: {repr(result)}")
        self.assertIn("e.g.", result[0])

    def test_vs_abbreviation_not_split(self):
        result = split_into_sentences("Red vs. Blue is better. We agree.")
        self.assertEqual(len(result), 2, f"Expected 2 sentences, got {result}: {repr(result)}")
        self.assertIn("vs.", result[0])

    # ---- Normal splitting still works ----

    def test_normal_period_still_splits(self):
        result = split_into_sentences("Hello world. How are you? Goodbye!")
        self.assertEqual(len(result), 3, f"Expected 3 sentences, got {result}: {repr(result)}")

    def test_cjk_sentence_enders_still_work(self):
        result = split_into_sentences("你好。世界！")
        self.assertGreaterEqual(len(result), 1)

    # ---- Edge cases ----

    def test_empty_input(self):
        self.assertEqual(split_into_sentences(""), [])
        self.assertEqual(split_into_sentences("   "), [])

    def test_newline_only_splits_by_line(self):
        result = split_into_sentences("Line one.\nLine two.")
        self.assertEqual(len(result), 2)


# ===========================================================================
# TESTS — Structural Code Paths (verify fixes are present in source)
# ===========================================================================


class TestStructuralCodePaths(unittest.TestCase):
    """Verify that bot-identified code paths exist and are correctly structured."""

    def setUp(self):
        # Derive repo root from this test file's location, works in any checkout
        # Test file lives at backend/tests/unit/<this_file> → go up 3 dirs
        self.pr_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

    def _read_source(self, filepath: str) -> str | None:
        try:
            with open(f"{self.pr_root}/backend/{filepath}") as f:
                return f.read()
        except FileNotFoundError:
            return None

    # --- Abbreviation protection ---

    def test_split_has_abbrev_protection(self):
        source = self._read_source("utils/translation.py")
        self.assertIsNotNone(source)
        self.assertIn("_ABBREV_PATTERNS", source, "split_into_sentences must have abbreviation protection patterns")

    def test_split_has_merge_heuristic(self):
        source = self._read_source("utils/translation.py")
        self.assertIsNotNone(source)
        self.assertIn("_should_merge", source, "split_into_sentences must have post-split merge heuristic")

    # --- Full-text cache before sentence splitting (P2) ---

    def test_translate_units_batch_has_full_text_cache_phase(self):
        source = self._read_source("utils/translation.py")
        self.assertIsNotNone(source)
        self.assertIn("full_text_results", source)
        phase_neg1 = source.index("# Phase -1:")
        phase_0 = source.index("# Phase 0:")
        self.assertLess(
            phase_neg1, phase_0, "Full-text cache check (Phase -1) must come before " "sentence splitting (Phase 0)"
        )

    # --- No-op path version bump + batch buffer clear (P1 from round 2) ---

    def test_no_op_path_bumps_version_and_clears_batch(self):
        source = self._read_source("utils/translation_coordinator.py")
        self.assertIsNotNone(source)
        self.assertIn("_next_version()", source)
        self.assertIn("_batch_buffer", source)
        no_op_section = source[
            source.index("should_persist_translation") : source.index("continue  # Don't add to batch buffer")
        ]
        self.assertIn(
            "_next_version()", no_op_section, "No-op path must bump version to invalidate stale batch entries"
        )
        self.assertIn("_batch_buffer", no_op_section, "No-op path must clear batch buffer for this segment")

    # --- Failed-fallback memory cache guard (P1 from round 2) ---

    def test_failed_fallback_guards_all_cache_writes(self):
        source = self._read_source("utils/translation.py")
        self.assertIsNotNone(source)
        self.assertIn("_failed_sent_hashes", source)
        set_mem_pos = source.rfind("_set_memory_cache")
        cache_trans_pos = source.rfind("cache_translation(text_hash")
        guard_pos = source.rfind("_failed_sent_hashes", 0, max(set_mem_pos, cache_trans_pos))
        self.assertGreater(guard_pos, -1, "_failed_sent_hashes guard not found")
        self.assertLess(guard_pos, set_mem_pos, "_set_memory_cache must be gated by _failed_sent_hashes")
        self.assertLess(guard_pos, cache_trans_pos, "cache_translation must be gated by _failed_sent_hashes")

    # --- Async Redis via run_blocking (P2 from round 2) ---

    def test_observe_offloads_redis_to_run_blocking(self):
        source = self._read_source("utils/translation_coordinator.py")
        self.assertIsNotNone(source)
        self.assertIn("run_blocking", source)
        observe_section = source[source.find("def observe") :]
        self.assertIn("run_blocking", observe_section)
        self.assertIn("get_cached_translation", observe_section)


if __name__ == "__main__":
    unittest.main()
