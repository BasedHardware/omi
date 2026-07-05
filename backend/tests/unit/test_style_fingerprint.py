import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("ENCRYPTION_SECRET", "test-secret-for-unit-tests-only-1234567890")

import utils.llm.style_fingerprint as sf  # noqa: E402


def test_tokenizer_counts_non_latin_scripts():
    # Cyrillic: 3 words + 2 words. The old ASCII-only [A-Za-z']+ matched nothing, so
    # each message collapsed to 1 word via `or 1` (avg_words would be 1.0).
    fp = sf.compute_fingerprint(["привет как дела", "все хорошо"])
    assert fp.avg_words == 2.5
    assert "привет" in fp.vocabulary
    assert "хорошо" in fp.vocabulary


def test_tokenizer_handles_accented_latin_and_apostrophes():
    fp = sf.compute_fingerprint(["café très bon", "don't stop"])  # 3 words + 2 ("don't" is one)
    assert fp.avg_words == 2.5
    assert "café" in fp.vocabulary
    assert "don't" in fp.vocabulary


def test_uses_emoji_at_exact_threshold_is_true():
    # 1 emoji across 20 messages -> emoji_rate == 0.05 exactly -> uses_emoji True (>=).
    samples = ["hello 🎉"] + ["plain message"] * 19
    fp = sf.compute_fingerprint(samples)
    assert fp.emoji_rate == 0.05
    assert fp.uses_emoji is True


def test_tokenizer_keeps_combining_marks_attached():
    import unicodedata

    # Decomposed Latin: "café" as c,a,f,e + combining acute -> one token, one word.
    decomposed = unicodedata.normalize("NFD", "café")
    assert sf._tokenize_words(decomposed) == [decomposed]
    fp = sf.compute_fingerprint([decomposed])
    assert fp.avg_words == 1.0

    # Devanagari (Hindi): vowel signs (Mc/Mn) attach to base consonants; the phrase
    # "नमस्ते दोस्त" is 2 words, not split on every matra.
    fp2 = sf.compute_fingerprint(["नमस्ते दोस्त"])
    assert fp2.avg_words == 2.0
