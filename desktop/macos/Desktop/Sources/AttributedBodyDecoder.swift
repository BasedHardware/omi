import Foundation

/// Decodes the message body from a Messages `attributedBody` blob.
///
/// On modern macOS `message.text` is frequently NULL and the real text lives in
/// `attributedBody`, an old-style typedstream (`streamtyped`) NSAttributedString
/// archive. `NSKeyedUnarchiver` cannot read it and `NSUnarchiver` is unavailable
/// in Swift, so we scan the typedstream bytes for the string body — the same
/// approach open-source iMessage exporters use.
///
/// This is best-effort and deliberately defensive: any malformed blob returns nil
/// rather than throwing, so a single bad row never breaks a sync. Callers should
/// prefer `message.text` when present and only fall back to this.
enum AttributedBodyDecoder {

  static func decode(_ data: Data) -> String? {
    let bytes = [UInt8](data)
    guard !bytes.isEmpty else { return nil }

    // The attributed string body follows the "NSString" (or "NSMutableString")
    // class marker in the typedstream.
    let marker = Array("NSString".utf8)
    guard let markerRange = firstRange(of: marker, in: bytes) else { return nil }

    // After the class name, typedstream emits a few control bytes and then a
    // 0x2B ('+') tag that introduces the inline string: <tag><length><utf8...>.
    var i = markerRange.upperBound
    guard let plusIndex = indexOf(0x2B, in: bytes, from: i) else { return nil }
    i = plusIndex + 1
    guard i < bytes.count else { return nil }

    // Length is a typedstream variable-length integer.
    var length = Int(bytes[i])
    i += 1
    if length == 0x81 {  // next 2 bytes, little-endian
      guard i + 1 < bytes.count else { return nil }
      length = Int(bytes[i]) | (Int(bytes[i + 1]) << 8)
      i += 2
    } else if length == 0x82 {  // next 4 bytes, little-endian
      guard i + 3 < bytes.count else { return nil }
      length =
        Int(bytes[i]) | (Int(bytes[i + 1]) << 8) | (Int(bytes[i + 2]) << 16) | (Int(bytes[i + 3]) << 24)
      i += 4
    }

    guard length > 0, i + length <= bytes.count else { return nil }
    let slice = bytes[i..<(i + length)]
    guard let text = String(bytes: slice, encoding: .utf8) else { return nil }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }

  /// Prefer the plain `text` column; fall back to decoding `attributedBody`.
  static func bestText(text: String?, attributedBody: Data?) -> String? {
    if let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      return text
    }
    if let attributedBody {
      return decode(attributedBody)
    }
    return nil
  }

  // MARK: - byte helpers

  private static func indexOf(_ byte: UInt8, in bytes: [UInt8], from start: Int) -> Int? {
    var i = max(0, start)
    while i < bytes.count {
      if bytes[i] == byte { return i }
      i += 1
    }
    return nil
  }

  private static func firstRange(of pattern: [UInt8], in bytes: [UInt8]) -> Range<Int>? {
    guard !pattern.isEmpty, bytes.count >= pattern.count else { return nil }
    let last = bytes.count - pattern.count
    var i = 0
    while i <= last {
      var match = true
      var j = 0
      while j < pattern.count {
        if bytes[i + j] != pattern[j] {
          match = false
          break
        }
        j += 1
      }
      if match { return i..<(i + pattern.count) }
      i += 1
    }
    return nil
  }
}
