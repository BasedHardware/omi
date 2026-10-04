import XCTest

@testable import OmiKit

final class SSEFrameDecoderTests: XCTestCase {
  func testUTF8AndEveryChunkBoundaryPreserveFrameText() {
    let frame = "event: delta\ndata: {\"text\":\"Café 你好 👋🏽\"}"
    let bytes = Array((frame + "\n\n").utf8)
    for split in 0...bytes.count {
      var decoder = SSEFrameDecoder()
      var frames = [String]()
      for chunk in [Array(bytes[..<split]), Array(bytes[split...])] {
        for byte in chunk {
          if let value = decoder.append(byte) { frames.append(value) }
        }
      }
      XCTAssertEqual(frames, [frame], "Chunk split at byte \(split)")
    }
  }

  func testCRLFCRAndBOMAreNormalizedWithoutEmptyFrames() {
    var decoder = SSEFrameDecoder()
    let bytes = Array("\u{FEFF}event: delta\r\ndata: 你好\r\n\r\n\r\nevent: done\rdata: {}\r\r".utf8)
    XCTAssertEqual(
      bytes.compactMap { decoder.append($0) },
      [
        "event: delta\ndata: 你好", "event: done\ndata: {}",
      ])
  }

  func testIncompleteFrameIsNotDeliveredAtEOF() {
    var decoder = SSEFrameDecoder()
    let delivered = Array("event: delta\ndata: partial\n".utf8)
      .compactMap { decoder.append($0) }
    XCTAssertTrue(delivered.isEmpty)
    XCTAssertEqual(decoder.append(10), "event: delta\ndata: partial")
  }

  func testFinishFlushesUnterminatedTrailingFrameOnce() {
    var decoder = SSEFrameDecoder()
    let bytes = Array("event: delta\ndata: 1\n\nevent: done\ndata: {\"ok\":\"é\"}".utf8)
    var frames = bytes.compactMap { decoder.append($0) }
    XCTAssertEqual(frames, ["event: delta\ndata: 1"])
    if let tail = decoder.finish() { frames.append(tail) }
    XCTAssertEqual(frames, ["event: delta\ndata: 1", "event: done\ndata: {\"ok\":\"é\"}"])
    XCTAssertNil(decoder.finish())
  }
}
