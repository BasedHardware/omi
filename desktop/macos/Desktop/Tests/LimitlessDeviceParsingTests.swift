import XCTest

@testable import Omi_Computer

/// Regression coverage for the protobuf length-delimited parsing in
/// `LimitlessDeviceConnection`. A malformed varint length (a 10-byte varint sets
/// bit 63 → `Int.min`, or a length larger than the buffer) previously trapped
/// `Array(data[pos..<pos + length])` and corrupted the cursor via `pos += length`,
/// crashing the app on a single corrupt BLE notification. The parser now clamps
/// every field length through `boundedFieldLength`.
@MainActor
final class LimitlessDeviceParsingTests: XCTestCase {

  // MARK: - boundedFieldLength (shared guard surface)

  func testBoundedFieldLengthClampsNegativeToZero() {
    // A 10-byte varint decodes to Int.min; the guard must reject it.
    XCTAssertEqual(LimitlessDeviceConnection.boundedFieldLength(Int.min, at: 3, count: 16), 0)
    XCTAssertEqual(LimitlessDeviceConnection.boundedFieldLength(-1, at: 0, count: 16), 0)
  }

  func testBoundedFieldLengthClampsOverlongToRemaining() {
    // Claimed length exceeds the buffer → consume only the remaining bytes.
    XCTAssertEqual(LimitlessDeviceConnection.boundedFieldLength(1_000_000, at: 4, count: 16), 12)
    XCTAssertEqual(LimitlessDeviceConnection.boundedFieldLength(Int.max, at: 0, count: 8), 8)
  }

  func testBoundedFieldLengthPassesValidLengthThrough() {
    XCTAssertEqual(LimitlessDeviceConnection.boundedFieldLength(5, at: 2, count: 16), 5)
    XCTAssertEqual(LimitlessDeviceConnection.boundedFieldLength(4, at: 12, count: 16), 4)
  }

  func testBoundedFieldLengthGuardsCursorAtOrBeyondEnd() {
    XCTAssertEqual(LimitlessDeviceConnection.boundedFieldLength(3, at: 16, count: 16), 0)
    XCTAssertEqual(LimitlessDeviceConnection.boundedFieldLength(3, at: -1, count: 16), 0)
  }

  // MARK: - parseBlePacket end-to-end (real production parse path)

  /// A field-4 (payload) length-delimited field whose length varint is a
  /// 10-byte sequence decoding to a negative value. Before the fix this trapped
  /// on the payload slice; now it must return without crashing.
  func testParseBlePacketSurvivesNegativeLengthVarint() {
    let connection = makeConnection()

    var packet: [UInt8] = []
    packet += [0x08, 0x05]  // field 1 (index) = 5
    packet += [0x18, 0x01]  // field 3 (numFrags) = 1
    packet += [0x22]  // field 4 (payload), wireType 2
    // 10-byte varint: nine continuation bytes then a terminator that sets bit 63.
    packet += Array(repeating: 0xFF, count: 9)
    packet += [0x7F]

    let result = connection.parseBlePacket(packet)

    // The malformed length is clamped to zero → empty payload, no trap.
    XCTAssertNotNil(result)
    XCTAssertEqual(result?.index, 5)
    XCTAssertEqual(result?.numFrags, 1)
    XCTAssertEqual(result?.payload.count, 0)
  }

  /// A payload length that overshoots the buffer must clamp to the remaining
  /// bytes rather than trap.
  func testParseBlePacketClampsOverlongPayloadLength() {
    let connection = makeConnection()

    var packet: [UInt8] = []
    packet += [0x08, 0x02]  // field 1 (index) = 2
    packet += [0x18, 0x01]  // field 3 (numFrags) = 1
    packet += [0x22, 0x40]  // field 4 (payload), claimed length = 64
    packet += [0xAA, 0xBB, 0xCC]  // only 3 bytes actually present

    let result = connection.parseBlePacket(packet)

    XCTAssertNotNil(result)
    XCTAssertEqual(result?.index, 2)
    XCTAssertEqual(result?.payload ?? [], [0xAA, 0xBB, 0xCC])
  }

  /// A length varint that is all continuation bytes (high bit set) with no
  /// terminator. The 10-byte varint cap bounds the read so the parser can't
  /// scan the whole buffer as one varint, and the clamped length keeps the
  /// slice empty — no trap, no hang.
  func testParseBlePacketSurvivesOverlongContinuationVarint() {
    let connection = makeConnection()

    var packet: [UInt8] = []
    packet += [0x08, 0x01]  // field 1 (index) = 1
    packet += [0x18, 0x01]  // field 3 (numFrags) = 1
    packet += [0x22]  // field 4 (payload), wireType 2
    packet += Array(repeating: 0xFF, count: 20)  // 20 continuation bytes, no terminator

    let result = connection.parseBlePacket(packet)

    XCTAssertNotNil(result)
    XCTAssertEqual(result?.index, 1)
    XCTAssertEqual(result?.payload.count, 0)
  }

  // MARK: - Flash-page / opus extraction (negative-varint OOB)

  /// A 10-byte varint whose terminator sets bit 63 decodes to a negative `Int`.
  /// The flash-page parsers computed `pos + length` / `min(pos + length, count)`
  /// straight from this value, driving the cursor negative and trapping the next
  /// `flashPageData[pos]` subscript. Every embedded length now routes through
  /// `boundedFieldLength`, which rejects length <= 0.
  private let negativeLengthVarint: [UInt8] = Array(repeating: 0xFF, count: 9) + [0x7F]

  func testParseFlashPageInfoSurvivesNegativeChunkLength() {
    let connection = makeConnection()
    var page: [UInt8] = [0x1a]  // field 3 (chunk), wire type 2
    page += negativeLengthVarint
    page += [0x00, 0x00, 0x00, 0x00]

    // Must not trap; malformed chunk is skipped, defaults returned.
    let info = connection.parseFlashPageInfo(page)
    XCTAssertEqual(info["did_start_session"] as? Bool, false)
    XCTAssertEqual(info["did_stop_recording"] as? Bool, false)
  }

  func testExtractOpusFramesSurvivesNegativeWrapperLength() {
    let connection = makeConnection()
    var page: [UInt8] = [0x1a]  // audio wrapper, wire type 2
    page += negativeLengthVarint
    page += [0x00, 0x00, 0x00, 0x00]

    let frames = connection.extractOpusFramesFromFlashPage(page)
    XCTAssertEqual(frames.count, 0)
  }

  /// A valid wrapper + valid audio field whose INNER length-delimited field has a
  /// negative varint length — the recursive extractor used to run `pos += length`
  /// unconditionally (the `length > 0` guard short-circuits), rewinding `pos`
  /// below `start` and trapping `data[pos]`.
  func testExtractOpusFramesSurvivesNegativeRecursiveInnerLength() {
    let connection = makeConnection()
    var recursiveTarget: [UInt8] = [0x0a]  // field 1, wire type 2
    recursiveTarget += negativeLengthVarint  // negative inner length (11 bytes total)
    let audioField: [UInt8] = [0x12, UInt8(recursiveTarget.count)] + recursiveTarget
    let wrapper: [UInt8] = [0x1a, UInt8(audioField.count)] + audioField
    let page = wrapper + [0x00, 0x00]

    let frames = connection.extractOpusFramesFromFlashPage(page)
    XCTAssertEqual(frames.count, 0)
  }

  // MARK: - Helpers

  private func makeConnection() -> LimitlessDeviceConnection {
    LimitlessDeviceConnection(
      device: bluetoothReliabilityTestDevice,
      transport: ReliabilityTestTransport(sessionGeneration: 1)
    )
  }
}
