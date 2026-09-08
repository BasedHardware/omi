import XCTest

@testable import Omi_Computer

/// Regression test for the dead Rewind "Rebuild Index" recovery path: the encoder
/// writes chunks as "<yyyy-MM-dd>/chunk_HHmmss_<epochMillis>_<unique>.mp4", but rebuild scanned for
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

  func testParsesCurrentUniqueMp4ChunkPathWithDayDirectory() throws {
    // The exact shape VideoChunkEncoder.generateChunkPath produces.
    let uniqueID = try XCTUnwrap(UUID(uuidString: "8E5D1E90-499B-491A-8D72-13CE7F344564"))
    let secondUniqueID = try XCTUnwrap(UUID(uuidString: "CF889709-57C5-4B9D-96EB-D7EC9BD20CF2"))
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = .current
    formatter.dateFormat = "yyyy-MM-dd HH:mm:ss.SSS"
    let captureTime = try XCTUnwrap(formatter.date(from: "2026-04-09 14:30:22.123"))
    let relativePath = VideoChunkEncoder.generateChunkPath(for: captureTime, uniqueID: uniqueID)

    let timestamp = try XCTUnwrap(
      RewindIndexer.parseChunkTimestamp(relativePath: relativePath)
    )
    XCTAssertEqual(timestamp.timeIntervalSince1970, captureTime.timeIntervalSince1970, accuracy: 0.001)
    XCTAssertNotEqual(
      relativePath,
      VideoChunkEncoder.generateChunkPath(for: captureTime, uniqueID: secondUniqueID),
      "same-second starts must get distinct persistent chunk paths"
    )

    let laterCaptureTime = captureTime.addingTimeInterval(0.500)
    let laterTimestamp = try XCTUnwrap(
      RewindIndexer.parseChunkTimestamp(
        relativePath: VideoChunkEncoder.generateChunkPath(for: laterCaptureTime, uniqueID: secondUniqueID)
      )
    )
    XCTAssertLessThan(timestamp, laterTimestamp, "recovery must retain ordering for chunks from the same second")
  }

  func testParsesLegacySecondGranularMp4ChunkPathWithDayDirectory() throws {
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
    XCTAssertNil(RewindIndexer.parseChunkTimestamp(relativePath: "2026-04-09/chunk_143022_.mp4"))  // empty suffix
    XCTAssertNil(RewindIndexer.parseChunkTimestamp(relativePath: "2026-04-09/chunk_143022_garbage.mp4"))
    XCTAssertNil(
      RewindIndexer.parseChunkTimestamp(relativePath: "2026-04-09/chunk_143022_123_.mp4")
    )  // empty unique suffix
    XCTAssertNil(
      RewindIndexer.parseChunkTimestamp(relativePath: "2026-04-09/chunk_143022_1784415936991_garbage.mp4")
    )  // invalid UUID
    XCTAssertNil(RewindIndexer.parseChunkTimestamp(relativePath: "chunk_143022.mp4"))  // no day dir, no legacy match
  }
}
