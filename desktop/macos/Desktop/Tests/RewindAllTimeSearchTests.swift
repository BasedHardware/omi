import XCTest

@testable import Omi_Computer

/// Rewind's search used to clamp both of its passes to the single day the timeline happened to be
/// showing, which made the one control able to reach the whole history the one control that could
/// not: a phrase read last week came back empty, indistinguishable from never having been read.
///
/// These drive the two reads that the unclamped search now depends on, against real rows in an
/// isolated throwaway storage root — no network, no embedding model, no clock.
final class RewindAllTimeSearchTests: XCTestCase {

  private var testUserId: String!
  private var storageRoot: URL!
  private var userDir: URL!
  private var previousLocalProfile: String?
  private var previousStorageName: String?

  override func setUp() async throws {
    try await super.setUp()

    // Redirect the *whole* storage root, not just the user folder. Run through the documented
    // `xcrun swift test --filter` command these suites write into the real
    // `~/Library/Application Support/Omi/users/` tree, and anything that ends a test before
    // `tearDown` (a trap in an assertion, a timeout) leaves a database behind in the user's own
    // data directory. A throwaway top-level root is removed whole and can never name a real user.
    previousLocalProfile = ProcessInfo.processInfo.environment["OMI_DESKTOP_LOCAL_PROFILE"]
    previousStorageName = ProcessInfo.processInfo.environment["OMI_LOCAL_PROFILE_STORAGE_NAME"]
    let storageName = "OmiTests-all-time-search-\(UUID().uuidString)"
    setenv("OMI_DESKTOP_LOCAL_PROFILE", "1", 1)
    setenv("OMI_LOCAL_PROFILE_STORAGE_NAME", storageName, 1)

    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    storageRoot = appSupport.appendingPathComponent(storageName, isDirectory: true)

    // Same lifecycle `RewindStorageTestIsolation` uses: the pool has to be closed and *retargeted*
    // to this suite's user. Setting `currentUserId` alone is not enough — a `configuredUserId` left
    // behind by an earlier suite in the same process outranks it, and the database would open for
    // that user instead.
    testUserId = "all-time-search-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await RewindStorageTestIsolation.invalidateAllStorageCaches()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    userDir =
      storageRoot
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)

    // Fail loudly rather than quietly writing into the user's real Omi directory if the storage
    // redirection ever stops working.
    XCTAssertTrue(
      FileManager.default.fileExists(atPath: userDir.appendingPathComponent("omi.db").path),
      "the test database must live under the throwaway storage root, not in the user's Omi data")
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    await RewindStorageTestIsolation.invalidateAllStorageCaches()
    await RewindDatabase.shared.configure(userId: nil)
    if let storageRoot { try? FileManager.default.removeItem(at: storageRoot) }
    RewindDatabase.currentUserId = nil
    if let previousLocalProfile {
      setenv("OMI_DESKTOP_LOCAL_PROFILE", previousLocalProfile, 1)
    } else {
      unsetenv("OMI_DESKTOP_LOCAL_PROFILE")
    }
    if let previousStorageName {
      setenv("OMI_LOCAL_PROFILE_STORAGE_NAME", previousStorageName, 1)
    } else {
      unsetenv("OMI_LOCAL_PROFILE_STORAGE_NAME")
    }
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
    if let embedding {
      let id = try XCTUnwrap(
        inserted.id, "a freshly inserted screenshot must carry the row id its embedding is keyed by")
      try await RewindDatabase.shared.updateScreenshotEmbedding(id: id, embedding: embedding)
    }
    return inserted
  }

  // MARK: - An inserted frame carries the row id the rest of capture is keyed by

  /// **This is what made the all-time semantic pass read an empty table.** `insertScreenshot`
  /// returns the record it wrote so the caller can key follow-up work to the new row, and the whole
  /// live embedding path is `if let id = inserted.id`. `Screenshot` declares
  /// `mutating func didInsert` to capture the auto-generated rowid, but a `PersistableRecord`'s
  /// `didInsert` requirement is non-mutating, so that method was never a witness for it: GRDB ran
  /// its empty default instead and every insert returned `id == nil`. Embeddings were then written
  /// only by the launch backfill, which marks itself complete — after which nothing newly captured
  /// was ever embedded, and a newest-first semantic scan looks at exactly those frames.
  func testInsertedScreenshotCarriesItsRowId() async throws {
    let inserted = try await insert(daysAgo: 0, text: "a frame the rest of capture must be able to name")
    let id = try XCTUnwrap(inserted.id, "insertScreenshot must return the row id it just generated")

    let stored = try await RewindDatabase.shared.getScreenshot(id: id)
    XCTAssertEqual(
      stored?.ocrText, "a frame the rest of capture must be able to name",
      "the returned row id must address the row that was just written")
  }

  // MARK: - Text search reaches past the day on screen

  func testUnclampedSearchFindsAMatchFromAnOlderDay() async throws {
    try await insert(daysAgo: 0, text: "today the quarterly ledger reconciled")
    try await insert(daysAgo: 23, text: "the peregrine migration notes were filed")

    // What the page now asks: no date bounds at all.
    let allTime = try await RewindDatabase.shared.search(query: "peregrine", startDate: nil, endDate: nil)
    XCTAssertEqual(allTime.count, 1, "an all-time search must reach a frame from three weeks ago")
    let match = try XCTUnwrap(allTime.first)
    XCTAssertTrue(match.ocrText?.contains("peregrine") == true)

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

    XCTAssertEqual(firstPage.count, 1, "an unbounded range must read the stored embeddings, not nothing")
    let newestRow = try XCTUnwrap(firstPage.first)
    let newest = try await RewindDatabase.shared.getScreenshot(id: newestRow.screenshotId)
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
    let onlyRow = try XCTUnwrap(windowed.first)
    let only = try await RewindDatabase.shared.getScreenshot(id: onlyRow.screenshotId)
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
