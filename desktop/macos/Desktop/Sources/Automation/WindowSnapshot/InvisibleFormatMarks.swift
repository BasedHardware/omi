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
/// label can read as another. So are the right-to-left mark (U+200F) and the
/// Arabic letter mark (U+061C): each is a strong right-to-left character, so
/// in a left-to-right line it moves the digits and spaces beside it
/// ("1234 \u{200F}5678" can read "5678 1234"). None of them is dropped
/// quietly where a person decides: the card shows each as its code point,
/// and a commit whose preview holds one offers only Deny.
///
/// The zero-width joiner (U+200D) and non-joiner (U+200C) are neither: they
/// hold emoji sequences and Persian words together, so message text keeps
/// them.
enum InvisibleFormatMarks {
  /// Marks that are invisible and reorder nothing: the left-to-right mark,
  /// the zero-width space, the word joiner and the invisible math operators,
  /// the byte-order mark, the soft hyphen and the Mongolian vowel separator.
  static func isHarmless(_ scalar: Unicode.Scalar) -> Bool {
    switch scalar.value {
    case 0x00AD, 0x180E, 0x200B, 0x200E, 0x2060...0x2064, 0xFEFF: return true
    default: return false
    }
  }

  /// Embeddings, overrides and isolates, which reorder the text after them,
  /// and the right-to-left and Arabic letter marks, which reorder the digits
  /// and spaces beside them.
  static func isBidiControl(_ scalar: Unicode.Scalar) -> Bool {
    switch scalar.value {
    case 0x061C, 0x200F, 0x202A...0x202E, 0x2066...0x2069: return true
    default: return false
    }
  }

  /// `text` without one U+200E or U+200F at its very start. An app's
  /// localised labels start with the mark of their own direction (WhatsApp
  /// starts English labels with U+200E, and a right-to-left locale's with
  /// U+200F); one there only sets the label's direction and moves nothing
  /// before it. Any other right-to-left mark, and every other bidirectional
  /// control, stays.
  static func strippingLeadingDirectionMark(_ text: String) -> String {
    guard let first = text.unicodeScalars.first, first == "\u{200E}" || first == "\u{200F}" else { return text }
    return String(String.UnicodeScalarView(text.unicodeScalars.dropFirst()))
  }

  /// Whether a label holds a bidirectional control other than one leading direction mark.
  static func labelContainsBidiControl(_ label: String) -> Bool {
    containsBidiControl(strippingLeadingDirectionMark(label))
  }

  /// `text` without U+200E LEFT-TO-RIGHT MARK, the one mark an app's own
  /// name is known to start with; every other invisible character is kept,
  /// so the card can show it as its code point.
  static func strippingLeftToRightMarks(_ text: String) -> String {
    guard text.unicodeScalars.contains("\u{200E}") else { return text }
    return String(String.UnicodeScalarView(text.unicodeScalars.filter { $0 != "\u{200E}" }))
  }

  /// `text` without its harmless marks; every other character, bidirectional controls included, is kept.
  static func strippingHarmless(_ text: String) -> String {
    guard text.unicodeScalars.contains(where: isHarmless) else { return text }
    return String(String.UnicodeScalarView(text.unicodeScalars.filter { !isHarmless($0) }))
  }

  /// Whether `text` holds a bidirectional embedding, override or isolate, or a right-to-left or Arabic letter mark.
  static func containsBidiControl(_ text: String) -> Bool {
    text.unicodeScalars.contains(where: isBidiControl)
  }
}
