import XCTest

@testable import Omi_Computer

/// Rewind's search used to clamp both of its passes to the single day the timeline happened to be
/// showing, which made the one control able to reach the whole history the one control that could
/// not: a phrase read last week came back empty, indistinguishable from never having been read.
///
/// These drive the two reads that the unclamped search now depends on, against real rows in an
/// isolated throwaway user directory — no network, no embedding model, no clock.
final class RewindAllTimeSearchTests: XCTestCase {

  private var testUserId: String!
  private var userDir: URL!

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "all-time-search-\(UUID().uuidString)"
    RewindDatabase.currentUserId = testUserId
    try await RewindDatabase.shared.initialize()

    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    RewindDatabase.currentUserId = nil
    try await super.tearDown()
  }

  @discardableResult
  private func insert(daysAgo: Int, text: String, embedding: Data? = nil) async throws -> Screenshot {
    let stamp = Calendar.current.date(byAdding: .day, value: -daysAgo, to: Date())!
    let inserted = try await RewindDatabase.shared.insertScreenshot(
      Screenshot(
        timestamp: stamp,
        appName: "AllTimeTest",
        videoChunkPath: "alltime/\(daysAgo).mp4",
        frameOffset: 0,
        ocrText: text,
        isIndexed: true))
    if let embedding, let id = inserted.id {
      try await RewindDatabase.shared.updateScreenshotEmbedding(id: id, embedding: embedding)
    }
    return inserted
  }

  // MARK: - Text search reaches past the day on screen

  func testUnclampedSearchFindsAMatchFromAnOlderDay() async throws {
    try await insert(daysAgo: 0, text: "today the quarterly ledger reconciled")
    try await insert(daysAgo: 23, text: "the peregrine migration notes were filed")

    // What the page now asks: no date bounds at all.
    let allTime = try await RewindDatabase.shared.search(query: "peregrine", startDate: nil, endDate: nil)
    XCTAssertEqual(allTime.count, 1, "an all-time search must reach a frame from three weeks ago")
    XCTAssertTrue(allTime[0].ocrText?.contains("peregrine") == true)

    // What it used to ask, and why the phrase was unfindable.
    let calendar = Calendar.current
    let todayStart = calendar.startOfDay(for: Date())
    let todayEnd = calendar.date(byAdding: .day, value: 1, to: todayStart)!
    let dayScoped = try await RewindDatabase.shared.search(
      query: "peregrine", startDate: todayStart, endDate: todayEnd)
    XCTAssertTrue(
      dayScoped.isEmpty,
      "precondition: the day-scoped query is exactly what hid the older match")
  }

  // MARK: - The semantic pass stays bounded once history is unlimited

  func testEmbeddingBatchReadsNewestFirstOverAnUnboundedRange() async throws {
    let blob = Data(repeating: 0, count: 4)
    try await insert(daysAgo: 40, text: "oldest", embedding: blob)
    try await insert(daysAgo: 5, text: "middle", embedding: blob)
    try await insert(daysAgo: 0, text: "newest", embedding: blob)

    // Unbounded range, budget of one row: the caller's budget must buy the *newest* frame.
    let firstPage = try await RewindDatabase.shared.readEmbeddingBatch(
      startDate: nil, endDate: nil, limit: 1, offset: 0)

    XCTAssertEqual(firstPage.count, 1)
    let newest = try await RewindDatabase.shared.getScreenshot(id: try XCTUnwrap(firstPage[0].screenshotId))
    XCTAssertEqual(
      newest?.ocrText, "newest",
      "a bounded scan of an all-time range must spend its budget on recent frames, not on 1970")
  }

  func testEmbeddingBatchStillHonoursAnExplicitRange() async throws {
    let blob = Data(repeating: 0, count: 4)
    try await insert(daysAgo: 40, text: "oldest", embedding: blob)
    try await insert(daysAgo: 0, text: "newest", embedding: blob)

    let calendar = Calendar.current
    let start = calendar.date(byAdding: .day, value: -60, to: Date())!
    let end = calendar.date(byAdding: .day, value: -30, to: Date())!
    let windowed = try await RewindDatabase.shared.readEmbeddingBatch(startDate: start, endDate: end)

    XCTAssertEqual(windowed.count, 1, "callers that pass a window must still get only that window")
    let only = try await RewindDatabase.shared.getScreenshot(id: try XCTUnwrap(windowed[0].screenshotId))
    XCTAssertEqual(only?.ocrText, "oldest")
  }

  // MARK: - The page knows how far back it goes

  /// Rewind plays one day at a time, so reaching the whole history means knowing which days hold
  /// any. This drives the real seek walk against real rows: the days that hold capture come back
  /// newest-first, the days that hold nothing are absent, and no day is reported twice.
  func testCapturedDayStartsReportsEveryDayThatHoldsCaptureNewestFirst() async throws {
    let calendar = Calendar.current
    // Days 0, 2 and 9 back hold capture; days 1 and 3–8 hold nothing at all.
    let offsets = [0, 2, 9]
    for offset in offsets {
      try await insert(daysAgo: offset, text: "span \(offset)")
      // A second frame the same day must not produce a second day.
      let stamp = calendar.date(byAdding: .day, value: -offset, to: Date())!
      _ = try await RewindDatabase.shared.insertScreenshot(
        Screenshot(
          timestamp: stamp.addingTimeInterval(120), appName: "AllTimeTest",
          videoChunkPath: "alltime/\(offset).mp4", frameOffset: 1, isIndexed: true))
    }

    let days = try await RewindDatabase.shared.capturedDayStarts()

    let expected = offsets.map {
      calendar.startOfDay(for: calendar.date(byAdding: .day, value: -$0, to: Date())!)
    }
    XCTAssertEqual(days, expected, "captured days must be exactly the days that hold rows, newest first")
    XCTAssertEqual(Set(days).count, days.count, "a day with several frames must appear once")
    XCTAssertEqual(days.last, expected.last, "the oldest captured day is what 'all time' reaches back to")
  }

  /// The walk must stop rather than run to the beginning of time on an empty database — the page
  /// calls it on every launch, including a first launch with no capture at all.
  func testCapturedDayStartsIsEmptyWhenNothingWasEverCaptured() async throws {
    let days = try await RewindDatabase.shared.capturedDayStarts()
    XCTAssertTrue(days.isEmpty, "an account with no capture must report no captured days, not a walk to 1970")
  }
}
