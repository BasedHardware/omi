import XCTest

@testable import Omi_Computer

final class WALFrameEncodingTests: XCTestCase {

  func testEncodeFramesUsesLengthPrefixLayout() {
    let frames = [Data([0xAA, 0xBB]), Data([0xCC])]
    let encoded = WALService.encodeFrames(frames)

    XCTAssertEqual(Array(encoded), [2, 0, 0, 0, 0xAA, 0xBB, 1, 0, 0, 0, 0xCC])
  }
}
