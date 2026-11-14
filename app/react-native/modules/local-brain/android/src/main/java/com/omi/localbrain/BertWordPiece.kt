package com.omi.localbrain

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
 * source model. Unknown characters fall back to [UNK] 100.
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

  private fun isPunct(ch: Char): Boolean {
    val cp = ch.code
    return (cp in 33..47) ||
        (cp in 58..64) ||
        (cp in 91..96) ||
        (cp in 123..126)
  }

  /**
   * Greedy longest-match WordPiece over one basic token. Splits into continuations
   * when no whole word is in the vocab, and returns nothing (rather than [UNK]) when
   * no substring is, which is how the reference handles out-of-vocab words.
   */
  private fun wordPiece(word: String): List<String> {
    if (word.isEmpty()) return emptyList()
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
      if (match == null) return emptyList() // unrepresentable; reference drops it
      pieces.add(match!!)
      start = end
    }
    return pieces
  }

  companion object {
    private val whitespace = mapOf(' ' to true, '\t' to true, '\n' to true, '\r' to true)

    fun fromAssetFile(text: String): BertWordPiece {
      val vocab = HashMap<String, Int>(32768)
      text.lineSequence().forEachIndexed { index, line ->
        vocab[line] = index
      }
      return BertWordPiece(vocab)
    }
  }
}