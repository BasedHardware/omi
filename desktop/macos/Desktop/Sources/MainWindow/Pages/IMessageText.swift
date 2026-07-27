import Foundation

/// Resolves the plain-text body of a Messages (`chat.db`) row.
///
/// On modern macOS the `message.text` column is usually **NULL** — the visible message string lives
/// in the `attributedBody` BLOB, an `NSAttributedString` archived with the legacy `NSArchiver`
/// "streamtyped" format (NOT `NSKeyedArchiver`, so `NSKeyedUnarchiver` cannot read it). A reader
/// that only looks at `text` therefore captures almost nothing recent. This helper returns `text`
/// when present, otherwise decodes the string out of `attributedBody`, otherwise nil.
///
/// The decoder is a minimal, defensive typedstream scanner — not a full unarchiver. It finds the
/// `NSString`/`NSMutableString` class marker, then reads the following length-prefixed UTF-8 bytes
/// that hold the message string. It never force-unwraps and returns nil on any malformed input, so
/// it is safe to run over an arbitrary on-device database blob. Self-contained: no dependencies.
enum IMessageText {
  /// The plain-text body for a message row. Prefers a non-empty `text` column; falls back to
  /// decoding the `attributedBody` typedstream blob; returns nil when neither yields text.
  static func body(text: String?, attributedBody: Data?) -> String? {
    if let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      return text
    }
    guard let attributedBody, !attributedBody.isEmpty else { return nil }
    return decodeAttributedBody(attributedBody)
  }

  /// Extract the message string from an `attributedBody` typedstream blob, or nil if it can't be
  /// found / decoded. Defensive by construction: every bounds check fails to nil rather than trapping.
  ///
  /// Layout (observed via `NSArchiver.archivedData(withRootObject: NSAttributedString(string:))`):
  ///
  ///   ... 4e 53 53 74 72 69 6e 67 ("NSString") .. 2b <len> <utf8 bytes> ...
  ///
  /// `0x2b` (`+`) marks an inline string; `<len>` is the UTF-8 **byte** count, encoded as a single
  /// byte when < 128, or an escape marker (`0x81` → next 2 bytes little-endian UInt16, `0x82` →
  /// next 4 bytes little-endian UInt32) for longer strings.
  static func decodeAttributedBody(_ data: Data) -> String? {
    let bytes = [UInt8](data)
    // "streamtyped" header + a class marker + a length + at least one byte of content.
    guard bytes.count > 12 else { return nil }

    // Locate the string object's class marker. `NSString` is the superclass emitted for both
    // immutable and mutable strings, and is never a substring of `NSMutableString` /
    // `NSAttributedString`, so a first-match search lands on the right region.
    let searchStart: Int
    if let idx = firstIndex(of: Array("NSString".utf8), in: bytes) {
      searchStart = idx + "NSString".count
    } else if let idx = firstIndex(of: Array("NSMutableString".utf8), in: bytes) {
      searchStart = idx + "NSMutableString".count
    } else {
      return nil
    }

    // The inline-string marker `+` (0x2b) precedes the length; the string content follows.
    guard let marker = indexOf(0x2b, in: bytes, from: searchStart) else { return nil }
    let lengthPos = marker + 1
    guard lengthPos < bytes.count else { return nil }

    guard let (length, contentStart) = readLength(bytes, at: lengthPos), length > 0,
      contentStart + length <= bytes.count
    else { return nil }

    return String(bytes: bytes[contentStart..<(contentStart + length)], encoding: .utf8)
  }

  /// Read a typedstream length starting at `pos`. Returns the length and the index of the first
  /// content byte, or nil on an unexpected marker or a truncated buffer.
  private static func readLength(_ bytes: [UInt8], at pos: Int) -> (length: Int, contentStart: Int)? {
    let marker = bytes[pos]
    switch marker {
    case 0x81:  // next 2 bytes: little-endian UInt16
      guard pos + 2 < bytes.count else { return nil }
      let value = Int(bytes[pos + 1]) | (Int(bytes[pos + 2]) << 8)
      return (value, pos + 3)
    case 0x82:  // next 4 bytes: little-endian UInt32
      guard pos + 4 < bytes.count else { return nil }
      let value =
        Int(bytes[pos + 1]) | (Int(bytes[pos + 2]) << 8) | (Int(bytes[pos + 3]) << 16)
        | (Int(bytes[pos + 4]) << 24)
      return (value, pos + 5)
    case 0x00..<0x80:  // single-byte length
      return (Int(marker), pos + 1)
    default:  // 0x80 / 0x83+ are not lengths here — bail defensively
      return nil
    }
  }

  /// Index of the first `byte` at or after `from`, or nil.
  private static func indexOf(_ byte: UInt8, in bytes: [UInt8], from: Int) -> Int? {
    guard from < bytes.count else { return nil }
    var i = from
    while i < bytes.count {
      if bytes[i] == byte { return i }
      i += 1
    }
    return nil
  }

  /// Index of the first occurrence of `needle` in `haystack`, or nil. Plain byte search — `needle`
  /// is always non-empty here.
  private static func firstIndex(of needle: [UInt8], in haystack: [UInt8]) -> Int? {
    guard !needle.isEmpty, haystack.count >= needle.count else { return nil }
    let last = haystack.count - needle.count
    var i = 0
    while i <= last {
      var match = true
      var j = 0
      while j < needle.count {
        if haystack[i + j] != needle[j] {
          match = false
          break
        }
        j += 1
      }
      if match { return i }
      i += 1
    }
    return nil
  }
}
