import XCTest

@testable import Omi_Computer

/// Regression test for the WAL duplicate-id data loss: two chunks sharing a WAL id
/// ("device_second", 1s resolution) share the same on-disk filename, and the
/// duplicate write atomically OVERWROTE the file with only the new buffer —
/// destroying the earlier ~60s of recorded audio while totalFrames claimed the
/// sum. A duplicate-id write must EXTEND the existing file instead.
final class WALFrameAppendTests: XCTestCase {

  func testEncodeFramesUsesLengthPrefixLayout() {
    let frames = [Data([0xAA, 0xBB]), Data([0xCC])]
    let encoded = WALService.encodeFrames(frames)
    // UInt32-LE length + bytes, per frame: [2,0,0,0, AA,BB, 1,0,0,0, CC]
    XCTAssertEqual(Array(encoded), [2, 0, 0, 0, 0xAA, 0xBB, 1, 0, 0, 0, 0xCC])
  }

  func testAppendExtendsExistingBytesInsteadOfOverwriting() {
    let existing = WALService.encodeFrames([Data([0x01, 0x02])])
    let newFrames = [Data([0x03])]

    let appended = WALService.frameFileBytes(existing: existing, frames: newFrames, append: true)

    // Prior frames are preserved and the new frame is appended after them.
    XCTAssertEqual(appended.prefix(existing.count), existing)
    XCTAssertEqual(appended, existing + WALService.encodeFrames(newFrames))
    XCTAssertGreaterThan(appended.count, existing.count)
  }

  func testNonAppendOverwritesWithNewFramesOnly() {
    let existing = WALService.encodeFrames([Data([0x01, 0x02])])
    let newFrames = [Data([0x03])]

    // append == false is the fresh-chunk path: only the new frames are written.
    let bytes = WALService.frameFileBytes(existing: existing, frames: newFrames, append: false)
    XCTAssertEqual(bytes, WALService.encodeFrames(newFrames))
  }

  func testAppendWithNoExistingFileWritesNewFramesOnly() {
    let newFrames = [Data([0x03])]
    let bytes = WALService.frameFileBytes(existing: nil, frames: newFrames, append: true)
    XCTAssertEqual(bytes, WALService.encodeFrames(newFrames))
  }
}
