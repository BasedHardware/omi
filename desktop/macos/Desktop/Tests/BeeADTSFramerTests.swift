import XCTest

@testable import Omi_Computer

/// Regression test for the Bee audio-parser wedge: a false ADTS sync whose
/// decoded frameLength is 0 (or any value < 7, the header size) used to be
/// accepted — `prefix(0)` returned an empty frame and `removeFirst(0)` advanced
/// nothing, so the corrupt header stayed at the buffer head and every later
/// packet re-hit it. Audio went permanently silent while the buffer grew without
/// bound. `nextADTSFrame` must treat frameLength < 7 as a false sync and advance.
final class BeeADTSFramerTests: XCTestCase {

  /// A valid 9-byte ADTS frame: header encodes frameLength = 9 (7 header + 2
  /// payload). frameLength = (b3&3)<<11 | b4<<3 | (b5&0xE0)>>5 = 0 | 8 | 1 = 9.
  private let validFrame: [UInt8] = [0xFF, 0xF1, 0x00, 0x00, 0x01, 0x20, 0x00, 0xAA, 0xBB]

  func testZeroLengthFalseSyncDoesNotWedgeOrReturnEmptyFrame() {
    // 0xFF 0xFx sync but frameLength bits all zero.
    var buffer: [UInt8] = [0xFF, 0xF1, 0x00, 0x00, 0x00, 0x00, 0x00]
    let frame = BeeDeviceConnection.nextADTSFrame(from: &buffer)
    // Must never emit an empty frame, and must make progress (consume the bad byte).
    XCTAssertNil(frame)
    XCTAssertLessThan(buffer.count, 7, "false sync byte must be consumed, not left to wedge")
  }

  func testRepeatedFalseSyncPacketsDrainInsteadOfGrowing() {
    // Simulate the wedge: a stream of frameLength-0 headers. Each drain call must
    // shrink the buffer rather than leaving it unchanged (which grew it unbounded).
    var buffer: [UInt8] = []
    for _ in 0..<10 { buffer.append(contentsOf: [0xFF, 0xF1, 0x00, 0x00, 0x00, 0x00, 0x00]) }
    var lastCount = buffer.count + 1
    while buffer.count >= 7 {
      _ = BeeDeviceConnection.nextADTSFrame(from: &buffer)
      XCTAssertLessThan(buffer.count, lastCount, "parser must always advance")
      lastCount = buffer.count
    }
    XCTAssertLessThan(buffer.count, 7)
  }

  func testValidFrameAfterFalseSyncIsRecovered() {
    var buffer: [UInt8] = [0xFF, 0xF1, 0x00, 0x00, 0x00, 0x00, 0x00] + validFrame
    var frames: [[UInt8]] = []
    while let f = BeeDeviceConnection.nextADTSFrame(from: &buffer) { frames.append(f) }
    XCTAssertEqual(frames.count, 1)
    XCTAssertEqual(frames.first, validFrame)
    XCTAssertTrue(buffer.isEmpty)
  }

  func testValidFrameIsExtractedIntact() {
    var buffer = validFrame
    let frame = BeeDeviceConnection.nextADTSFrame(from: &buffer)
    XCTAssertEqual(frame, validFrame)
    XCTAssertTrue(buffer.isEmpty)
  }
}
