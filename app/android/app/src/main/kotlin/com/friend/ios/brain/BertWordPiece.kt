package com.friend.ios.brain

/**
 * A minimal BERT WordPiece tokenizer, matching `BertTokenizerFast` from
 * `sentence-transformers/all-MiniLM-L6-v2`.
 *
 * The router graph takes pre-tokenized int64 ids, and the Python tokenizer cannot
 * run on a phone, so an on-device tokenizer is what turns this from a probe over
 * fixed utterances into something that accepts arbitrary input. The contract below
 * was read off the reference implementation rather than guessed:
 *
 *   lowercase          do_lower_case = true
 *   split              whitespace + punctuation, each punctuation its own token
 *   wordpiece          greedy longest-match-first, "##" prefix on continuations
 *   special tokens     [CLS] 101 ... [SEP] 102, [PAD] 0
 *   padding            fixed width (128 here), mask 0 over padding
 *
 * Verified against the reference on the cases that matter most, including the
 * typo path: "turn onn the flashlught" ->
 * [turn, on, ##n, the, flash, ##lu, ##ght].
 *
 * The vocabulary is `vocab.txt` (30,522 rows) in assets, shipped as-is from the
 * source model. Unknown words fall back to [UNK] 100 rather than being dropped --
 * see [wordPiece] for why that distinction matters.
 */
class BertWordPiece(vocab: Map<String, Int>) {

  private val vocab: Map<String, Int> = vocab

  fun encode(text: String, seqLength: Int): Pair<LongArray, LongArray> {
    val pieces = ArrayList<Int>(seqLength)

    // [CLS]
    pieces.add(vocab["[CLS]"] ?: 101)

    val words =
        basicTokenize(text.lowercase())
            .map { wordPiece(it) }
            .flatten()
            .filter { it.isNotEmpty() }
    // Reserve one slot for [SEP]; truncate if the utterance is longer.
    for (piece in words) {
      if (pieces.size >= seqLength - 1) break
      pieces.add(vocab[piece] ?: (vocab["[UNK]"] ?: 100))
    }
    pieces.add(vocab["[SEP]"] ?: 102)

    val ids = LongArray(seqLength) { vocab["[PAD]"]?.toLong() ?: 0L }
    val mask = LongArray(seqLength)
    for (i in pieces.indices) {
      ids[i] = pieces[i].toLong()
      mask[i] = 1L
    }
    return Pair(ids, mask)
  }

  /** Whitespace + punctuation split, one token per punctuation mark. */
  private fun basicTokenize(text: String): List<String> {
    val out = ArrayList<String>()
    val current = StringBuilder()
    for (ch in text) {
      val c = whitespace[ch]
      if (c != null) {
        if (current.isNotEmpty()) {
          out.add(current.toString())
          current.setLength(0)
        }
        continue
      }
      if (isPunct(ch)) {
        if (current.isNotEmpty()) {
          out.add(current.toString())
          current.setLength(0)
        }
        out.add(ch.toString())
        continue
      }
      current.append(ch)
    }
    if (current.isNotEmpty()) out.add(current.toString())
    return out
  }

  /**
   * Whether a character splits a token, following the reference's `_is_punctuation`:
   * the four ASCII ranges, plus every Unicode `P*` category.
   *
   * The ASCII ranges alone left smart quotes and dashes attached to their
   * neighbours, so "don’t" arrived as one word and "yes—and" as one word, and
   * WordPiece then discarded those glued tokens outright. That is invisible in the
   * happy path and quietly damaging on real dictation, which is full of curly
   * quotes. The typed constants are used rather than magic numbers so a wrong
   * ordinal cannot slip in.
   */
  private fun isPunct(ch: Char): Boolean {
    val cp = ch.code
    if ((cp in 33..47) || (cp in 58..64) || (cp in 91..96) || (cp in 123..126)) return true
    return when (Character.getType(ch)) {
      // These constants are declared byte in java.lang.Character while getType()
      // returns int, so they need widening to be comparable here.
      Character.CONNECTOR_PUNCTUATION.toInt(),
      Character.DASH_PUNCTUATION.toInt(),
      Character.START_PUNCTUATION.toInt(),
      Character.END_PUNCTUATION.toInt(),
      Character.INITIAL_QUOTE_PUNCTUATION.toInt(),
      Character.FINAL_QUOTE_PUNCTUATION.toInt(),
      Character.OTHER_PUNCTUATION.toInt() -> true
      else -> false
    }
  }

  /**
   * Greedy longest-match WordPiece over one basic token. Splits into continuations
   * when no whole word is in the vocab.
   *
   * An unrepresentable word becomes [UNK] rather than disappearing. Returning empty
   * here looked equivalent -- encode() filters empty results -- but it silently
   * deletes the word from the utterance, so an out-of-vocab word contributed nothing
   * to the embedding and the router scored the request as if those words had never
   * been said. That is worse than a coarse embedding: it is an input the model was
   * never shown. It also contradicted this class's own contract, which documents
   * [UNK] 100 as the fallback.
   */
  private fun wordPiece(word: String): List<String> {
    if (word.isEmpty()) return emptyList()

    // The reference caps a word at 100 characters and emits [UNK] beyond that. Without
    // the cap the longest-match loop below tries every shorter substring of the word,
    // which is quadratic in its length and runs on the routing worker thread -- one
    // pathological token would stall routing behind it.
    if (word.length > MAX_CHARS_PER_WORD) return listOf(UNK)

    if (vocab.containsKey(word)) return listOf(word)

    val pieces = ArrayList<String>()
    var start = 0
    while (start < word.length) {
      var end = word.length
      var match: String? = null
      while (start < end) {
        val candidate = if (start == 0) word.substring(0, end) else "##" + word.substring(start, end)
        if (vocab.containsKey(candidate)) {
          match = candidate
          break
        }
        end--
      }
      if (match == null) return listOf(UNK)
      pieces.add(match!!)
      start = end
    }
    return pieces
  }

  companion object {
    private val whitespace = mapOf(' ' to true, '\t' to true, '\n' to true, '\r' to true)

    /** Reference cap on a single word before [UNK]; see [wordPiece]. */
    private const val MAX_CHARS_PER_WORD = 100

    private const val UNK = "[UNK]"

    fun fromAssetFile(text: String): BertWordPiece {
      val vocab = HashMap<String, Int>(32768)
      text.lineSequence().forEachIndexed { index, line ->
        vocab[line] = index
      }
      return BertWordPiece(vocab)
    }
  }
}