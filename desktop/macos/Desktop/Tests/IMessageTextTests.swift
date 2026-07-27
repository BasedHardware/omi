import XCTest

@testable import Omi_Computer

/// Verifies `IMessageText` — the shared helper that resolves a Messages (`chat.db`) row's plain-text
/// body. On modern macOS `message.text` is usually NULL and the string lives only in the
/// `attributedBody` typedstream BLOB, so this decoder is what keeps the People thread-ingester from
/// capturing almost nothing recent.
///
/// Fixtures are real `NSArchiver` "streamtyped" blobs captured as hex (byte-compatible with what
/// Messages writes), so the test is hermetic and does not touch any private database or a deprecated
/// runtime API. No user messages are read.
final class IMessageTextTests: XCTestCase {

  // MARK: - Captured streamtyped fixtures (attributedBody for a known string)

  /// `NSArchiver.archivedData(withRootObject: NSAttributedString(string: "Hi"))` — single-byte length.
  private let hiBlob =
    "040b73747265616d747970656481e803840140848484124e5341747472696275746564537472696e67008484084e534f"
    + "626a656374008592848484084e53537472696e67019484012b02486986840269490102928484840c4e5344696374696f"
    + "6e6172790094840169008686"

  /// Same encoding for "Hey 👋 let's grab 🍕 at 6" — multi-byte UTF-8 (emoji + apostrophe).
  private let emojiBlob =
    "040b73747265616d747970656481e803840140848484124e5341747472696275746564537472696e67008484084e534f"
    + "626a656374008592848484084e53537472696e67019484012b1d48657920f09f918b206c65742773206772616220f09f"
    + "8d95206174203686840269490119928484840c4e5344696374696f6e6172790094840169008686"

  /// A 162-byte string ("The quick brown fox jumps. " × 6) — exercises the `0x81` 2-byte length path.
  private let longBlob =
    "040b73747265616d747970656481e803840140848484124e5341747472696275746564537472696e67008484084e534f"
    + "626a656374008592848484084e53537472696e67019484012b81a20054686520717569636b2062726f776e20666f7820"
    + "6a756d70732e2054686520717569636b2062726f776e20666f78206a756d70732e2054686520717569636b2062726f77"
    + "6e20666f78206a756d70732e2054686520717569636b2062726f776e20666f78206a756d70732e205468652071756963"
    + "6b2062726f776e20666f78206a756d70732e2054686520717569636b2062726f776e20666f78206a756d70732e208684"
    + "0269490181a200928484840c4e5344696374696f6e6172790094840169008686"

  /// "1 + 1 = 2, right? +++yes" — the content itself contains `+` (0x2b), the same byte used as the
  /// inline-string marker; the decoder must lock onto the marker BEFORE the content, not a `+` in it.
  private let plusBlob =
    "040b73747265616d747970656481e803840140848484124e5341747472696275746564537472696e67008484084e534f"
    + "626a656374008592848484084e53537472696e67019484012b1831202b2031203d20322c2072696768743f202b2b2b79"
    + "657386840269490118928484840c4e5344696374696f6e6172790094840169008686"

  private func data(_ hex: String) -> Data {
    let clean = hex.filter { !$0.isWhitespace }
    var bytes = [UInt8]()
    var idx = clean.startIndex
    while idx < clean.endIndex {
      let next = clean.index(idx, offsetBy: 2)
      guard let byte = UInt8(clean[idx..<next], radix: 16) else { return Data() }
      bytes.append(byte)
      idx = next
    }
    return Data(bytes)
  }

  // MARK: - Decoding the attributedBody blob

  func testDecodesKnownAsciiString() {
    XCTAssertEqual(
      IMessageText.decodeAttributedBody(data(hiBlob)), "Hi",
      "the ASCII message string is decoded out of the streamtyped attributedBody blob")
  }

  func testDecodesEmojiAndUnicode() {
    XCTAssertEqual(
      IMessageText.decodeAttributedBody(data(emojiBlob)), "Hey 👋 let's grab 🍕 at 6",
      "multi-byte UTF-8 (emoji, curly apostrophe) round-trips byte-for-byte")
  }

  func testDecodesLongStringWithTwoByteLength() {
    let expected = String(repeating: "The quick brown fox jumps. ", count: 6)
    XCTAssertEqual(expected.utf8.count, 162, "sanity: fixture is > 127 bytes so it uses the 0x81 length escape")
    XCTAssertEqual(
      IMessageText.decodeAttributedBody(data(longBlob)), expected,
      "a >127-byte string is decoded via the 2-byte (0x81) length encoding")
  }

  func testDecodesStringContainingPlusMarkerByte() {
    XCTAssertEqual(
      IMessageText.decodeAttributedBody(data(plusBlob)), "1 + 1 = 2, right? +++yes",
      "a '+' inside the message text does not confuse the inline-string marker scan")
  }

  // MARK: - body(): prefer text, fall back to blob, else nil

  func testBodyPrefersNonEmptyTextColumn() {
    XCTAssertEqual(
      IMessageText.body(text: "actual text", attributedBody: data(hiBlob)), "actual text",
      "when the text column has content it wins and the blob is not decoded")
  }

  func testBodyFallsBackToBlobWhenTextNilOrBlank() {
    XCTAssertEqual(
      IMessageText.body(text: nil, attributedBody: data(hiBlob)), "Hi",
      "a NULL text column falls back to decoding attributedBody")
    XCTAssertEqual(
      IMessageText.body(text: "   \n", attributedBody: data(hiBlob)), "Hi",
      "a whitespace-only text column also falls back to the blob")
  }

  func testBodyReturnsNilWhenNoContent() {
    XCTAssertNil(IMessageText.body(text: nil, attributedBody: nil), "no text and no blob → nil")
    XCTAssertNil(IMessageText.body(text: "", attributedBody: Data()), "empty text and empty blob → nil")
    XCTAssertNil(IMessageText.body(text: "  ", attributedBody: nil), "blank text and no blob → nil")
  }

  // MARK: - Malformed input never crashes and returns nil

  func testDecodeReturnsNilOnGarbage() {
    XCTAssertNil(IMessageText.decodeAttributedBody(Data()), "empty data → nil, no crash")
    XCTAssertNil(
      IMessageText.decodeAttributedBody(Data([0x00, 0x01, 0x02, 0x03, 0x2b, 0x05, 0x41, 0x42])),
      "random bytes with no NSString marker → nil")
    XCTAssertNil(
      IMessageText.decodeAttributedBody(Data(repeating: 0xff, count: 64)),
      "high-byte noise → nil, no crash")
  }

  func testDecodeReturnsNilOnTruncatedLength() {
    // "…NSString…+" with a 0x81 escape claiming 2 length bytes that don't exist → must not read OOB.
    let marker = Array("NSString".utf8) + [0x01, 0x94, 0x84, 0x01, 0x2b, 0x81]
    XCTAssertNil(
      IMessageText.decodeAttributedBody(Data(marker)),
      "a length escape past the end of the buffer returns nil instead of trapping")
  }

  func testDecodeReturnsNilWhenLengthExceedsBuffer() {
    // Valid NSString marker + `+`, then a length byte (0xc8) that is not a valid single-byte length
    // or known escape, with only a few content bytes following. Must return nil, never read OOB.
    let bytes = Array("NSString".utf8) + [0x2b, 0xc8, 0x41, 0x42, 0x43]
    XCTAssertNil(
      IMessageText.decodeAttributedBody(Data(bytes)),
      "a length that overruns the buffer returns nil (0xc8 is a non-length marker anyway)")
  }
}
