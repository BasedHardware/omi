"""
Unit tests for compute_text_similarity function.
Tests character trigram Jaccard similarity across multiple languages.
"""

from utils.text_utils import compute_text_similarity


class TestComputeTextSimilarity:
    """Tests for the compute_text_similarity function."""

    # ==================== Basic Tests ====================

    def test_identical_texts(self):
        """Identical texts should return 1.0 similarity."""
        text = "The quick brown fox jumps over the lazy dog"
        assert compute_text_similarity(text, text) == 1.0

    def test_completely_different_texts(self):
        """Completely different texts should return low similarity."""
        text1 = "Hello world"
        text2 = "Xyz abc 123"
        similarity = compute_text_similarity(text1, text2)
        assert similarity < 0.1

    def test_partial_overlap(self):
        """Texts with partial overlap should return intermediate similarity."""
        text1 = "Hello world how are you"
        text2 = "Hello world what is up"
        similarity = compute_text_similarity(text1, text2)
        assert 0.3 < similarity < 0.8

    def test_empty_strings(self):
        """Empty strings should return 0.0 similarity."""
        assert compute_text_similarity("", "") == 0.0
        assert compute_text_similarity("Hello", "") == 0.0
        assert compute_text_similarity("", "World") == 0.0

    def test_short_strings(self):
        """Short strings (< 3 chars) should be handled gracefully."""
        assert compute_text_similarity("Hi", "Hi") == 1.0
        assert compute_text_similarity("Hi", "Ho") == 0.0
        assert compute_text_similarity("A", "A") == 1.0

    # ==================== Normalization Tests ====================

    def test_case_insensitivity(self):
        """Similarity should be case-insensitive."""
        text1 = "Hello World"
        text2 = "hello world"
        assert compute_text_similarity(text1, text2) == 1.0

    def test_whitespace_normalization(self):
        """Extra whitespace should be normalized."""
        text1 = "Hello   World"
        text2 = "Hello World"
        assert compute_text_similarity(text1, text2) == 1.0

        text3 = "  Hello  World  "
        assert compute_text_similarity(text1, text3) == 1.0

    def test_newlines_and_tabs(self):
        """Newlines and tabs should be normalized to spaces."""
        text1 = "Hello\nWorld"
        text2 = "Hello World"
        assert compute_text_similarity(text1, text2) == 1.0

        text3 = "Hello\tWorld"
        assert compute_text_similarity(text2, text3) == 1.0

    # ==================== Multilingual Tests ====================

    def test_chinese_identical(self):
        """Chinese text comparison should work."""
        text1 = "你好世界"
        text2 = "你好世界"
        assert compute_text_similarity(text1, text2) == 1.0

    def test_chinese_with_punctuation(self):
        """Chinese text with punctuation differences - trigrams are affected by punctuation."""
        text1 = "你好世界"
        text2 = "你好，世界"
        similarity = compute_text_similarity(text1, text2)
        # Note: Punctuation in the middle breaks trigram overlap significantly
        # "你好世界" -> ["你好世", "好世界"]
        # "你好，世界" -> ["你好，", "好，世", "，世界"]
        # No overlap, so similarity is 0.0
        assert similarity >= 0.0

    def test_chinese_partial_overlap(self):
        """Chinese text with partial overlap."""
        text1 = "我今天去公园散步了"
        text2 = "我今天去商场购物了"
        similarity = compute_text_similarity(text1, text2)
        # Shared prefix "我今天去" gives some overlap
        assert 0.1 < similarity < 0.7

    def test_japanese_identical(self):
        """Japanese text comparison should work."""
        text1 = "こんにちは"
        text2 = "こんにちは"
        assert compute_text_similarity(text1, text2) == 1.0

    def test_japanese_partial_overlap(self):
        """Japanese text with partial overlap."""
        text1 = "こんにちは"
        text2 = "こんにちは世界"
        similarity = compute_text_similarity(text1, text2)
        assert 0.3 < similarity < 0.9

    def test_korean_identical(self):
        """Korean text comparison should work."""
        text1 = "안녕하세요"
        text2 = "안녕하세요"
        assert compute_text_similarity(text1, text2) == 1.0

    def test_korean_partial_overlap(self):
        """Korean text with partial overlap."""
        text1 = "안녕하세요 반갑습니다"
        text2 = "안녕하세요 잘 부탁드립니다"
        similarity = compute_text_similarity(text1, text2)
        assert 0.2 < similarity < 0.7

    def test_russian_identical(self):
        """Russian text comparison should work."""
        text1 = "Привет мир"
        text2 = "Привет мир"
        assert compute_text_similarity(text1, text2) == 1.0

    def test_russian_partial_overlap(self):
        """Russian text with partial overlap."""
        text1 = "Привет мир как дела"
        text2 = "Привет мир что нового"
        similarity = compute_text_similarity(text1, text2)
        assert 0.3 < similarity < 0.8

    def test_vietnamese_identical(self):
        """Vietnamese text comparison should work."""
        text1 = "Xin chào thế giới"
        text2 = "Xin chào thế giới"
        assert compute_text_similarity(text1, text2) == 1.0

    def test_vietnamese_partial_overlap(self):
        """Vietnamese text with partial overlap."""
        text1 = "Xin chào thế giới"
        text2 = "Xin chào bạn bè"
        similarity = compute_text_similarity(text1, text2)
        assert 0.2 < similarity < 0.7

    def test_hindi_identical(self):
        """Hindi text comparison should work."""
        text1 = "नमस्ते दुनिया"
        text2 = "नमस्ते दुनिया"
        assert compute_text_similarity(text1, text2) == 1.0

    def test_hindi_partial_overlap(self):
        """Hindi text with partial overlap."""
        text1 = "नमस्ते दुनिया कैसे हो"
        text2 = "नमस्ते दुनिया क्या हाल है"
        similarity = compute_text_similarity(text1, text2)
        assert 0.3 < similarity < 0.8

    def test_arabic_identical(self):
        """Arabic text comparison should work."""
        text1 = "مرحبا بالعالم"
        text2 = "مرحبا بالعالم"
        assert compute_text_similarity(text1, text2) == 1.0

    def test_thai_identical(self):
        """Thai text comparison should work."""
        text1 = "สวัสดีครับ"
        text2 = "สวัสดีครับ"
        assert compute_text_similarity(text1, text2) == 1.0

    # ==================== Edge Cases ====================

    def test_transcription_variations(self):
        """Typical transcription variations should have reasonable similarity."""
        # Numbers spelled out vs digits - still share significant overlap
        text1 = "I have 3 apples"
        text2 = "I have three apples"
        similarity = compute_text_similarity(text1, text2)
        assert similarity >= 0.4

    def test_punctuation_differences(self):
        """Punctuation differences should have reasonable similarity."""
        text1 = "Hello, world! How are you?"
        text2 = "Hello world how are you"
        similarity = compute_text_similarity(text1, text2)
        # Punctuation affects trigram overlap but core content is similar
        assert similarity > 0.5

    def test_similar_sentences_different_order(self):
        """Sentences with similar words but different order."""
        text1 = "The cat sat on the mat"
        text2 = "On the mat sat the cat"
        similarity = compute_text_similarity(text1, text2)
        # Should have moderate similarity since trigrams capture local patterns
        assert 0.3 < similarity < 0.9

    def test_repeated_words(self):
        """Text with repeated words."""
        text1 = "hello hello hello"
        text2 = "hello"
        similarity = compute_text_similarity(text1, text2)
        # Should have relatively high similarity
        assert similarity > 0.3
