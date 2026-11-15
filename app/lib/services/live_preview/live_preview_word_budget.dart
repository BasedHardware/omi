import 'package:characters/characters.dart';

/// A deterministic word budget, not a linguistic tokenizer. Han, Kana,
/// Hangul syllables and Thai runs cost one word per two graphemes (rounded
/// up); other non-whitespace runs cost one word. Script transitions end a
/// run, so mixed-language text cannot hide an unspaced run inside one word.
/// Keep this rule aligned with LivePreviewNotesPolicy.wordRanges in Swift.
abstract final class LivePreviewWordBudget {
  static int count(String text) => _ranges(text).length;

  static String first(String text, int words) {
    final ranges = _ranges(text);
    if (ranges.isEmpty || words <= 0) return '';
    return text.substring(ranges.first.start, ranges[(words - 1).clamp(0, ranges.length - 1)].end);
  }

  static String last(String text, int words) {
    final ranges = _ranges(text);
    if (ranges.isEmpty || words <= 0) return '';
    return text.substring(ranges[(ranges.length - words).clamp(0, ranges.length - 1)].start, ranges.last.end);
  }

  static List<({int start, int end})> _ranges(String text) {
    final ranges = <({int start, int end})>[];
    var offset = 0;
    int? start;
    var unspaced = false;
    var graphemes = 0;
    void flush() {
      if (start != null) ranges.add((start: start!, end: offset));
      start = null;
      graphemes = 0;
    }

    for (final character in text.characters) {
      final nextUnspaced = _isUnspaced(character.runes.first);
      if (character.trim().isEmpty) {
        flush();
      } else {
        if (start != null && (nextUnspaced != unspaced || (unspaced && graphemes == 2))) flush();
        start ??= offset;
        unspaced = nextUnspaced;
        graphemes++;
      }
      offset += character.length;
    }
    flush();
    return ranges;
  }

  static bool _isUnspaced(int rune) =>
      (rune >= 0x3400 && rune <= 0x9fff) || // Han
      (rune >= 0xf900 && rune <= 0xfaff) ||
      (rune >= 0x20000 && rune <= 0x323af) ||
      (rune >= 0x3040 && rune <= 0x30ff) || // Hiragana and Katakana
      (rune >= 0x31f0 && rune <= 0x31ff) ||
      (rune >= 0xff66 && rune <= 0xff9f) ||
      (rune >= 0xac00 && rune <= 0xd7a3) || // Hangul syllables
      (rune >= 0x0e00 && rune <= 0x0e7f); // Thai (combining marks stay with their grapheme)
}
