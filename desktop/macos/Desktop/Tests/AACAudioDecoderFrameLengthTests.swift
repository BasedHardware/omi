import XCTest

@testable import Omi_Computer

/// Regression coverage for ADTS frame-length parsing in `AACAudioDecoder`.
///
/// Bee-device audio is AAC and arrives over BLE, where payloads can be corrupt or
/// truncated. A malformed ADTS header whose 13-bit frame-length field decoded to a
/// value `<= 7` (the header size) previously reached `data.subdata(in: 7..<frameLength)`,
/// forming an invalid `Range` (`lowerBound > upperBound`) and trapping the whole
/// process. These tests pin that such frames are rejected (nil) rather than crashing,
/// and that well-formed frames still yield the correct payload range — including for
/// `Data` slices whose `startIndex` is not zero.
final class AACAudioDecoderFrameLengthTests: XCTestCase {
  /// Builds a minimal ADTS frame header (7 bytes) encoding `frameLength`, padded so
  /// the returned `Data` has at least `totalCount` bytes.
  private func makeADTSFrame(frameLength: Int, totalCount: Int, validSync: Bool = true) -> Data {
    var bytes = [UInt8](repeating: 0, count: max(7, totalCount))
    bytes[0] = validSync ? 0xFF : 0x00
    bytes[1] = validSync ? 0xF0 : 0x00
    // frameLength is 13 bits split across byte 3 (high 2), byte 4 (mid 8), byte 5 (low 3).
    bytes[3] = UInt8((frameLength >> 11) & 0x03)
    bytes[4] = UInt8((frameLength >> 3) & 0xFF)
    bytes[5] = UInt8((frameLength & 0x07) << 5)
    return Data(bytes)
  }

  func testMalformedShortFrameLengthReturnsNilInsteadOfTrapping() {
    // frameLength values 0...7 do not extend past the 7-byte header. Each of these
    // would have produced an invalid `7..<frameLength` range before the fix.
    for frameLength in 0...7 {
      let frame = makeADTSFrame(frameLength: frameLength, totalCount: 16)
      XCTAssertNil(
        AACAudioDecoder.adtsRawAACRange(in: frame),
        "frameLength \(frameLength) must be rejected, not turned into a subdata range"
      )
    }
  }

  func testWellFormedFrameReturnsPayloadRange() {
    let frameLength = 20
    let frame = makeADTSFrame(frameLength: frameLength, totalCount: frameLength)
    let range = AACAudioDecoder.adtsRawAACRange(in: frame)
    XCTAssertEqual(range, 7..<20)
  }

  func testIncompleteFrameReturnsNil() {
    // Header claims 40 bytes but only 16 are present.
    let frame = makeADTSFrame(frameLength: 40, totalCount: 16)
    XCTAssertNil(AACAudioDecoder.adtsRawAACRange(in: frame))
  }

  func testInvalidSyncWordReturnsNil() {
    let frame = makeADTSFrame(frameLength: 20, totalCount: 20, validSync: false)
    XCTAssertNil(AACAudioDecoder.adtsRawAACRange(in: frame))
  }

  func testTooShortDataReturnsNil() {
    XCTAssertNil(AACAudioDecoder.adtsRawAACRange(in: Data([0xFF, 0xF0, 0x00])))
  }

  func testNonZeroStartIndexSliceIsHandledWithoutTrapping() {
    // A Data slice whose startIndex != 0 must be parsed in its own index space.
    let frameLength = 20
    let full = Data([0x11, 0x22, 0x33]) + makeADTSFrame(frameLength: frameLength, totalCount: frameLength)
    let slice = full.suffix(from: full.startIndex + 3)  // startIndex == 3
    XCTAssertNotEqual(slice.startIndex, 0)
    let range = AACAudioDecoder.adtsRawAACRange(in: slice)
    XCTAssertEqual(range, (slice.startIndex + 7)..<(slice.startIndex + frameLength))
  }

  func testMalformedShortFrameLengthOnSliceReturnsNil() {
    // The crash case, but on a non-zero-startIndex slice.
    let full = Data([0x11, 0x22, 0x33]) + makeADTSFrame(frameLength: 5, totalCount: 16)
    let slice = full.suffix(from: full.startIndex + 3)
    XCTAssertNil(AACAudioDecoder.adtsRawAACRange(in: slice))
  }
}
