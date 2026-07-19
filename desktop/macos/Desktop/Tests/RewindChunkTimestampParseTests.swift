import XCTest

@testable import Omi_Computer

/// Regression test for the dead Rewind "Rebuild Index" recovery path: the encoder
/// writes chunks as "<yyyy-MM-dd>/chunk_HHmmss.mp4", but rebuild scanned for
/// ".hevc" and parsed a flat "chunk_YYYYMMDD_HHMMSS.hevc" (26-char) name — so it
/// recovered ZERO frames and silently reported success. The parser must read the
/// day from the path directory and accept the real .mp4 chunk shape.
final class RewindChunkTimestampParseTests: XCTestCase {

  private func localString(_ date: Date) -> String {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = .current
    f.dateFormat = "yyyy-MM-dd HH:mm:ss"
    return f.string(from: date)
  }

  func testParsesNewMp4ChunkPathWithDayDirectory() throws {
    // The exact shape VideoChunkEncoder.generateChunkPath produces.
    let date = try XCTUnwrap(
      RewindIndexer.parseChunkTimestamp(relativePath: "2026-04-09/chunk_143022.mp4"))
    XCTAssertEqual(localString(date), "2026-04-09 14:30:22")
  }

  func testRoundTripsWithLegacyHevcExtensionInNewLayout() throws {
    // A legacy .hevc file still stored under the day-directory layout.
    let date = try XCTUnwrap(
      RewindIndexer.parseChunkTimestamp(relativePath: "2026-01-02/chunk_000501.hevc"))
    XCTAssertEqual(localString(date), "2026-01-02 00:05:01")
  }

  func testParsesLegacyFlatHevcName() throws {
    let date = try XCTUnwrap(
      RewindIndexer.parseChunkTimestamp(relativePath: "chunk_20260409_143022.hevc"))
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.dateFormat = "yyyy-MM-dd HH:mm:ss"
    XCTAssertEqual(f.string(from: date), "2026-04-09 14:30:22")
  }

  func testRejectsMalformedNames() {
    XCTAssertNil(RewindIndexer.parseChunkTimestamp(relativePath: "2026-04-09/notachunk.mp4"))
    XCTAssertNil(RewindIndexer.parseChunkTimestamp(relativePath: "2026-04-09/chunk_14302.mp4"))  // 5 digits
    XCTAssertNil(RewindIndexer.parseChunkTimestamp(relativePath: "2026-04-09/chunk_1430aa.mp4"))  // non-numeric
    XCTAssertNil(RewindIndexer.parseChunkTimestamp(relativePath: "chunk_143022.mp4"))  // no day dir, no legacy match
  }
}
