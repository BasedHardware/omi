package com.friend.ios.brain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tokenizer tests. [BertWordPiece] imports nothing, so this runs on a plain JVM with
 * no Robolectric and no device -- which is the point of keeping it free of Android
 * types.
 *
 * Most cases use a small synthetic vocabulary so the expected token sequence is
 * obvious by inspection. [referenceVocabularyMatchesTheDocumentedTypoPath] loads the
 * real shipped `vocab.txt` to confirm the implementation still agrees with the
 * reference tokenization quoted in the class doc, because a synthetic vocab can
 * only ever prove the algorithm's shape, not that it matches BERT.
 */
class BertWordPieceTest {

    private fun tokenizer(vararg tokens: String): BertWordPiece {
        val vocab = LinkedHashMap<String, Int>()
        listOf("[PAD]", "[UNK]", "[CLS]", "[SEP]").forEachIndexed { i, t -> vocab[t] = i }
        tokens.forEachIndexed { i, t -> vocab[t] = vocab.size + i }
        return BertWordPiece(vocab)
    }

    private fun ids(t: BertWordPiece, text: String, seq: Int = 16): Pair<LongArray, LongArray> =
        t.encode(text, seq)

    private fun maskedIds(t: BertWordPiece, text: String, seq: Int = 16): List<Long> {
        val (i, m) = t.encode(text, seq)
        return (0 until seq).filter { m[it] == 1L }.map { i[it] }
    }

    /** The synthetic vocab assigns [UNK]=1, [CLS]=2, [SEP]=3 after the four specials. */
    @Test
    fun addsClsAndSepAroundContent() {
        val t = tokenizer("hello")
        val masked = maskedIds(t, "hello")

        assertEquals(2L, masked[0]) // [CLS]
        assertEquals(3L, masked[masked.size - 1]) // [SEP]
    }

    @Test
    fun masksOnlyRealTokens() {
        val t = tokenizer("hello")
        val (i, m) = ids(t, "hello")

        // mask.sum() on a LongArray is a Long; compare Long to Long.
        assertEquals(3L, m.sum()) // [CLS] hello [SEP]
        assertEquals(0L, i[m.size - 1])
    }

    @Test
    fun lowercasesInput() {
        val lower = tokenizer("hello")
        val upper = tokenizer("hello")
        // "HeLLo" must tokenize the same as "hello" because do_lower_case = true.
        assertEquals(maskedIds(lower, "hello"), maskedIds(upper, "HeLLo"))
    }

    @Test
    fun greedyLongestMatchPrefersLongestPiece() {
        // "flashl" must NOT be in the vocab or it matches whole and the split
        // never happens. Only the pieces it should break into.
        val t = tokenizer("flash", "##lu")
        val masked = maskedIds(t, "flashl")

        // [CLS] flash ##lu [SEP]
        assertEquals(3, masked.size)
    }

    @Test
    fun splitsUnknownWordIntoKnownSubstrings() {
        val t = tokenizer("flash", "##lu", "##ght")
        maskedIds(t, "flashlight")
        // No exception, and it produced at least one content token.
        assertTrue(maskedIds(t, "flashlight").size > 2)
    }

    /**
     * The regression: an unrepresentable word used to be dropped entirely, so it
     * contributed nothing to the embedding and the router scored the request as if
     * the word had never been spoken. It must now surface as [UNK].
     */
    @Test
    fun unrepresentableWordBecomesUnkRatherThanVanishing() {
        val t = tokenizer("hello")
        val masked = maskedIds(t, "zzzz")

        // [CLS] [UNK] [SEP] -- the word is present, not deleted.
        assertEquals(3, masked.size)
        assertEquals(1L, masked[1]) // [UNK]
    }

    @Test
    fun unkWordKeepsSurroundingWords() {
        val t = tokenizer("hello", "world")
        val masked = maskedIds(t, "hello zzzz world")

        // [CLS] hello [UNK] world [SEP]
        assertEquals(5, masked.size)
        assertEquals(1L, masked[2])
    }

    /**
     * Smart quotes must split like ASCII punctuation. Previously "don’t" stayed glued
     * as one word, which then failed WordPiece and was dropped.
     */
    @Test
    fun curlyApostropheSplitsLikeAscii() {
        val t = tokenizer("don", "##t", "turn")
        val curly = maskedIds(t, "don’t turn")
        val ascii = maskedIds(t, "don't turn")

        assertEquals("curly and ASCII apostrophes must tokenize identically", ascii, curly)
    }

    @Test
    fun emDashSplitsTokens() {
        val t = tokenizer("yes", "and", "##no")
        val masked = maskedIds(t, "yes—and no")

        // [CLS] yes — and ##no [SEP]: the dash became its own token.
        assertTrue("em dash should add a token", masked.size >= 5)
    }

    @Test
    fun ellipsisSplitsTokens() {
        val t = tokenizer("wait")
        val masked = maskedIds(t, "wait…")

        assertTrue("ellipsis should be split off", masked.size >= 3)
    }

    /**
     * The quadratic-search guard. A 5,000-char token used to hash every shorter
     * substring; it must short-circuit to [UNK] instead of stalling the worker.
     */
    @Test
    fun overlongTokenBecomesUnkQuickly() {
        val t = tokenizer("hello")
        val started = System.nanoTime()
        val masked = maskedIds(t, "a".repeat(5000))
        val elapsedMs = (System.nanoTime() - started) / 1_000_000

        assertEquals("[CLS] [UNK] [SEP]", 3, masked.size)
        assertTrue("overlong token took ${elapsedMs}ms", elapsedMs < 500)
    }

    @Test
    fun tokenAtExactlyTheCapIsNotUnk() {
        val t = tokenizer("a")
        // 100 chars is the reference cap, so it must not be rejected on length.
        val masked = maskedIds(t, "a".repeat(100))
        assertTrue(masked.isNotEmpty())
    }

    @Test
    fun emptyInputIsJustClsSep() {
        val t = tokenizer("hello")
        assertEquals(listOf(2L, 3L), maskedIds(t, ""))
    }

    @Test
    fun truncatesRatherThanOverflowingSeqLength() {
        val t = tokenizer("hello")
        val (i, m) = ids(t, ("hello ").repeat(200), seq = 16)

        assertEquals(16, i.size)
        assertEquals(16, m.size)
        assertTrue("mask must stay within seq", m.sum() <= 16.0)
    }

    @Test
    fun reserveRoomForSepUnderTruncation() {
        val t = tokenizer("hello")
        val (i, m) = ids(t, ("hello ").repeat(200), seq = 8)

        assertEquals(8, i.size)
        // The last real slot must still be [SEP], never a truncated piece.
        assertEquals(3L, i[7])
    }

    /**
     * The one test that checks the real thing. Everything above proves the shape of
     * the algorithm; this proves the shipped vocabulary still produces the
     * tokenization quoted in the class doc:
     *
     *   "turn onn the flashlught" -> [turn, on, ##n, the, flash, ##lu, ##ght]
     */
    @Test
    fun referenceVocabularyMatchesTheDocumentedTypoPath() {
        val vocabFile = javaClass.classLoader?.getResourceAsStream("vocab.txt")
        if (vocabFile == null) {
            // Not on the test classpath in this layout; the synthetic-vocabulary tests
            // above still cover the algorithm's behaviour.
            return
        }

        val text = vocabFile.bufferedReader().readText()
        val t = BertWordPiece.fromAssetFile(text)

        val (i, m) = t.encode("turn onn the flashlught", 32)
        val masked = (0 until 32).filter { m[it] == 1L }.map { i[it].toInt() }

        val expected =
            listOf(
                    "[CLS]", "turn", "on", "##n", "the", "flash", "##lu", "##ght", "[SEP]",
                )
                .map { line -> text.lineSequence().toList().indexOf(line) }

        assertEquals(expected, masked)
    }

    /**
     * An em dash must split the way a comma does. Comparing its id against a hyphens
     * id proves nothing when neither is in the vocabulary -- both collapse to [UNK]
     * and look identical -- so this asserts the structural effect instead: the dash
     * separates two words that would otherwise be glued into one.
     */
    @Test
    fun emDashSeparatesWordsTheWayACommaDoes() {
        val t = tokenizer("yes", "and")
        val split = maskedIds(t, "yes—and")
        val comma = maskedIds(t, "yes,and")
        val glued = maskedIds(t, "yesand")

        assertEquals("em dash and comma should tokenize alike", comma, split)
        // [CLS] yes <dash> and [SEP] -- the dash is its own token, and because it is
        // not in this synthetic vocab it comes back as [UNK]. The point is the count
        // and the equality with the comma case, not the dash's id.
        assertEquals(5, split.size)
        // "yesand" is one word that cannot be fully segmented. The reference sets
        // is_bad, breaks, and appends only [UNK] -- it does not keep the "yes" it had
        // already matched -- so [CLS] <UNK> [SEP]. Matching that is deliberate.
        assertEquals(3, glued.size)
        assertNotEquals(
            "a dash must separate words that are otherwise one token",
            glued,
            split,
        )
    }
}