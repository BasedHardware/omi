import Foundation

/// The invisible format characters another app's text can hold, sorted by
/// what they can do.
///
/// Apps put some of them around their own words for layout: WhatsApp starts
/// nearly every label, and its own display name, with U+200E LEFT-TO-RIGHT
/// MARK ("\u{200E}Send"). These marks change no letter and cannot move text
/// across a word, so Omi drops them wherever it shows, matches or compares
/// app text; shown as code points they only made "Send" unreadable.
///
/// The bidirectional embeddings, overrides and isolates (U+202A–U+202E,
/// U+2066–U+2069) are different: they reorder everything after them, so one
/// label can read as another. They are never dropped quietly where a person
/// decides: the card shows each as its code point, and a commit whose
/// preview holds one offers only Deny.
///
/// The zero-width joiner (U+200D) and non-joiner (U+200C) are neither: they
/// hold emoji sequences and Persian words together, so message text keeps
/// them.
enum InvisibleFormatMarks {
  /// Marks that are invisible and reorder nothing: the left-to-right,
  /// right-to-left and Arabic letter marks, the zero-width space, the word
  /// joiner and the invisible math operators, the byte-order mark, the soft
  /// hyphen and the Mongolian vowel separator.
  static func isHarmless(_ scalar: Unicode.Scalar) -> Bool {
    switch scalar.value {
    case 0x00AD, 0x061C, 0x180E, 0x200B, 0x200E, 0x200F, 0x2060...0x2064, 0xFEFF: return true
    default: return false
    }
  }

  /// Embeddings, overrides and isolates: they reorder the text after them.
  static func isBidiControl(_ scalar: Unicode.Scalar) -> Bool {
    switch scalar.value {
    case 0x202A...0x202E, 0x2066...0x2069: return true
    default: return false
    }
  }

  /// `text` without its harmless marks; every other character, bidirectional controls included, is kept.
  static func strippingHarmless(_ text: String) -> String {
    guard text.unicodeScalars.contains(where: isHarmless) else { return text }
    return String(String.UnicodeScalarView(text.unicodeScalars.filter { !isHarmless($0) }))
  }

  /// Whether `text` holds a bidirectional embedding, override or isolate.
  static func containsBidiControl(_ text: String) -> Bool {
    text.unicodeScalars.contains(where: isBidiControl)
  }
}
