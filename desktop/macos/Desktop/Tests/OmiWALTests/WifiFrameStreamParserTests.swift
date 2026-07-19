import XCTest

@testable import OmiWAL

/// Regression coverage for `WifiFrameStreamParser` block-boundary tracking.
///
/// The device streams audio in fixed 440-byte blocks; a `0` size byte is
/// padding that runs to the next block boundary. The parser used to compute
/// that boundary from the per-call buffer offset, so once one incomplete frame
/// was carried into the next chunk the boundary math desynced and every
/// subsequent padding jump dropped audio. The parser now tracks the absolute
/// stream offset across calls.
final class WifiFrameStreamParserTests: XCTestCase {
  private let toc: UInt8 = 0xb8  // a valid Opus TOC byte

  /// Build one 440-byte block: a single `[size][opus…]` frame, zero-padded.
  private func paddedBlock(payloadLength: Int) -> Data {
    var block = Data()
    block.append(UInt8(payloadLength))
    block.append(toc)
    block.append(contentsOf: Array(repeating: UInt8(0xaa), count: payloadLength - 1))
    block.append(contentsOf: Array(repeating: UInt8(0), count: WifiFrameStreamParser.blockSize - block.count))
    XCTAssertEqual(block.count, WifiFrameStreamParser.blockSize)
    return block
  }

  func testPaddingBoundaryStaysAlignedAcrossChunkSplits() {
    // Three blocks, each one frame followed by padding.
    let stream = paddedBlock(payloadLength: 10) + paddedBlock(payloadLength: 10)
      + paddedBlock(payloadLength: 10)

    // Feed the stream in awkward chunk sizes that split blocks mid-padding and
    // mid-frame — exactly the case that desynced the old buffer-relative math.
    var parser = WifiFrameStreamParser()
    var frames: [Data] = []
    var buffer = Data()
    for chunkStart in stride(from: 0, to: stream.count, by: 137) {
      let end = min(chunkStart + 137, stream.count)
      buffer.append(stream.subdata(in: chunkStart..<end))
      let (parsed, remaining) = parser.parse(buffer)
      frames.append(contentsOf: parsed)
      buffer = remaining
    }
    let (tail, _) = parser.parse(buffer)
    frames.append(contentsOf: tail)

    XCTAssertEqual(frames.count, 3, "every block's frame must be recovered despite chunk splits")
    XCTAssertEqual(parser.consumedStreamBytes, stream.count)
    for frame in frames {
      XCTAssertEqual(frame.first, toc)
      XCTAssertEqual(frame.count, 10)
    }
  }

  func testSinglePassParsesEveryBlock() {
    let stream = (0..<5).reduce(into: Data()) { acc, _ in acc.append(paddedBlock(payloadLength: 20)) }
    var parser = WifiFrameStreamParser()
    let (frames, remaining) = parser.parse(stream)
    XCTAssertEqual(frames.count, 5)
    XCTAssertTrue(remaining.isEmpty)
    XCTAssertEqual(parser.consumedStreamBytes, stream.count)
  }

  func testIncompleteTrailingFrameIsHeldAsRemaining() {
    var parser = WifiFrameStreamParser()
    // A size byte promising 50 payload bytes but only 5 delivered.
    var partial = Data([50, toc])
    partial.append(contentsOf: Array(repeating: UInt8(0xaa), count: 4))
    let (frames, remaining) = parser.parse(partial)
    XCTAssertTrue(frames.isEmpty, "an incomplete frame must not be emitted")
    XCTAssertEqual(remaining, partial, "the whole partial frame is held for the next chunk")
    XCTAssertEqual(parser.consumedStreamBytes, 0)
  }
}
