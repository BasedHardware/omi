import XCTest

@testable import Omi_Computer

/// Rewind's search used to clamp both of its passes to the single day the timeline happened to be
/// showing, which made the one control able to reach the whole history the one control that could
/// not: a phrase read last week came back empty, indistinguishable from never having been read.
///
/// These drive the two reads that the unclamped search now depends on, against real rows in an
/// isolated throwaway storage root — no network, no embedding model, no clock.
final class RewindAllTimeSearchTests: XCTestCase {

  /// The only fixture `tearDown` needs back. The suite's user id and its user directory are used
  /// where they are made, so they stay local to `setUp` rather than becoming implicitly unwrapped
  /// state a later test could read before it was written.
  private var storageRoot: URL?
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

    let appSupport = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first,
      "the user domain must have an Application Support directory to redirect storage into")
    let storageRoot = appSupport.appendingPathComponent(storageName, isDirectory: true)
    self.storageRoot = storageRoot

    // Same lifecycle `RewindStorageTestIsolation` uses: the pool has to be closed and *retargeted*
    // to this suite's user. Setting `currentUserId` alone is not enough — a `configuredUserId` left
    // behind by an earlier suite in the same process outranks it, and the database would open for
    // that user instead.
    let testUserId = "all-time-search-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await RewindStorageTestIsolation.invalidateAllStorageCaches()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let userDir =
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

  // MARK: - One clock, one zone, for both halves of every day-bucket assertion

  /// The zone every local day in this suite is expressed in.
  ///
  /// Pinned for the same reason `ContextBucketPromptAssemblerTests` pins it: it is never the CI
  /// runner's zone, so a regression that goes back to bucketing in `Calendar.current` fails on a
  /// UTC runner instead of staying green there.
  private static let seedZoneIdentifier = "America/New_York"

  /// One reading of the clock, in a zone that does not come from the machine.
  ///
  /// **Both halves of a day-bucket assertion must come from the same instant and the same zone.**
  /// Seeding from one `Date()` and deriving the expectation from another lets the two straddle
  /// local midnight; taking the zone from `Calendar.current` is the same defect in space rather
  /// than in time, because a UTC runner and a developer at UTC-4 disagree about which local day an
  /// evening frame belongs to. Everything below is derived from a single `Date()`, read once.
  private struct SeedClock {
    let calendar: Calendar

    /// Local noon of the day *before* the run.
    ///
    /// Yesterday rather than today because `capturedDayStarts` walks back from the live `Date()`
    /// and can never see a row seeded into the future — an anchor at today's noon is in the future
    /// for every run before midday. Noon rather than the current time of day because a within-day
    /// offset added to a noon anchor cannot reach either midnight.
    let noon: Date

    /// The anchor shifted back `daysAgo` local days, still at local noon.
    func instant(daysAgo: Int) throws -> Date {
      try XCTUnwrap(
        calendar.date(byAdding: .day, value: -daysAgo, to: noon),
        "the seeded day must be representable in the pinned calendar")
    }

    /// Where the local day `daysAgo` days before the anchor begins.
    func dayStart(daysAgo: Int) throws -> Date {
      calendar.startOfDay(for: try instant(daysAgo: daysAgo))
    }

    /// The last instant that still belongs to that local day.
    ///
    /// Asked of the calendar rather than computed as `start + 23:59:59`, so a 23-hour spring-forward
    /// day does not spill the frame into the following day — which is the whole hazard this suite
    /// exists to pin down, in its other form.
    func dayEnd(daysAgo: Int) throws -> Date {
      let start = try dayStart(daysAgo: daysAgo)
      let next = try XCTUnwrap(
        calendar.date(byAdding: .day, value: 1, to: start),
        "the day after a seeded day must be representable in the pinned calendar")
      return next.addingTimeInterval(-30)
    }
  }

  private func makeSeedClock() throws -> SeedClock {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(
      TimeZone(identifier: Self.seedZoneIdentifier),
      "the pinned seed zone must exist in the system time zone database")
    let today = calendar.startOfDay(for: Date())
    let yesterday = try XCTUnwrap(
      calendar.date(byAdding: .day, value: -1, to: today),
      "the day before the run must be representable in the pinned calendar")
    return SeedClock(calendar: calendar, noon: yesterday.addingTimeInterval(12 * 3600))
  }

  @discardableResult
  private func insert(
    at stamp: Date, text: String, appName: String = "AllTimeTest", embedding: Data? = nil
  ) async throws -> Screenshot {
    let inserted = try await RewindDatabase.shared.insertScreenshot(
      Screenshot(
        timestamp: stamp,
        appName: appName,
        videoChunkPath: "alltime/\(stamp.timeIntervalSince1970).mp4",
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
    let clock = try makeSeedClock()
    let inserted = try await insert(
      at: try clock.instant(daysAgo: 0), text: "a frame the rest of capture must be able to name")
    let id = try XCTUnwrap(inserted.id, "insertScreenshot must return the row id it just generated")

    let stored = try await RewindDatabase.shared.getScreenshot(id: id)
    XCTAssertEqual(
      stored?.ocrText, "a frame the rest of capture must be able to name",
      "the returned row id must address the row that was just written")
  }

  // MARK: - Text search reaches past the day on screen

  func testUnclampedSearchFindsAMatchFromAnOlderDay() async throws {
    let clock = try makeSeedClock()
    try await insert(at: try clock.instant(daysAgo: 0), text: "today the quarterly ledger reconciled")
    try await insert(at: try clock.instant(daysAgo: 23), text: "the peregrine migration notes were filed")

    // What the page now asks: no date bounds at all.
    let allTime = try await RewindDatabase.shared.search(query: "peregrine", startDate: nil, endDate: nil)
    XCTAssertEqual(allTime.count, 1, "an all-time search must reach a frame from three weeks ago")
    let match = try XCTUnwrap(allTime.first)
    XCTAssertTrue(match.ocrText?.contains("peregrine") == true)

    // What it used to ask, and why the phrase was unfindable. The bound is the seeded day in the
    // pinned zone, so the window is the one the newer frame actually sits in on any machine.
    let todayStart = try clock.dayStart(daysAgo: 0)
    let todayEnd = try XCTUnwrap(
      clock.calendar.date(byAdding: .day, value: 1, to: todayStart))
    let dayScoped = try await RewindDatabase.shared.search(
      query: "peregrine", startDate: todayStart, endDate: todayEnd)
    XCTAssertTrue(
      dayScoped.isEmpty,
      "precondition: the day-scoped query is exactly what hid the older match")
  }

  // MARK: - The semantic pass stays bounded once history is unlimited

  func testEmbeddingBatchReadsNewestFirstOverAnUnboundedRange() async throws {
    let clock = try makeSeedClock()
    let blob = Data(repeating: 0, count: 4)
    try await insert(at: try clock.instant(daysAgo: 40), text: "oldest", embedding: blob)
    try await insert(at: try clock.instant(daysAgo: 5), text: "middle", embedding: blob)
    try await insert(at: try clock.instant(daysAgo: 0), text: "newest", embedding: blob)

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
    let clock = try makeSeedClock()
    let blob = Data(repeating: 0, count: 4)
    try await insert(at: try clock.instant(daysAgo: 40), text: "oldest", embedding: blob)
    try await insert(at: try clock.instant(daysAgo: 0), text: "newest", embedding: blob)

    let start = try clock.instant(daysAgo: 60)
    let end = try clock.instant(daysAgo: 30)
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
    let clock = try makeSeedClock()
    // Days 0, 2 and 9 back from the anchor hold capture; days 1 and 3–8 hold nothing at all.
    let offsets = [0, 2, 9]
    for offset in offsets {
      // The two frames sit at the two ends of one local day *by construction*, which is the claim
      // the assertion below rests on. They used to be a live-clock stamp and that stamp plus two
      // minutes — same-day only if the run did not happen in the last two minutes of a day. On
      // 2026-08-15 at 23:58 it did: each second frame landed after midnight and reported a day one
      // newer than the one it was meant to duplicate, so three seeded days came back as five.
      // Seeding the day's first and last instants also drives the boundary the old fixture never
      // reached — a day is one day even when its capture touches both of its edges.
      try await insert(
        at: try clock.dayStart(daysAgo: offset).addingTimeInterval(30),
        text: "span \(offset)")
      _ = try await RewindDatabase.shared.insertScreenshot(
        Screenshot(
          timestamp: try clock.dayEnd(daysAgo: offset), appName: "AllTimeTest",
          videoChunkPath: "alltime/\(offset).mp4", frameOffset: 1, isIndexed: true))
    }

    // The pinned calendar, not the machine's: on a UTC runner these rows straddle two UTC days.
    let days = try await RewindDatabase.shared.capturedDayStarts(calendar: clock.calendar)

    let expected = try offsets.map { try clock.dayStart(daysAgo: $0) }
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

  // MARK: - The continuous timeline reaches retained history

  func testHistorySurveyPublishesGlobalBoundsWithoutReplacingTheVisibleWindow() async throws {
    let clock = try makeSeedClock()
    let newest = try await insert(at: try clock.instant(daysAgo: 0), text: "newest day")
    try await insert(at: try clock.instant(daysAgo: 2), text: "middle day")
    let oldest = try await insert(at: try clock.instant(daysAgo: 9), text: "oldest day")

    let viewModel = await MainActor.run { RewindViewModel() }
    await viewModel.surveyCapturedHistory(attempts: 1)
    let snapshot = await MainActor.run {
      (dayCount: viewModel.capturedDays.count, range: viewModel.historyRange, count: viewModel.screenshots.count)
    }

    XCTAssertEqual(snapshot.dayCount, 3)
    XCTAssertEqual(
      snapshot.count, 0, "surveying bounds must not replace the current viewport with a fixed all-time sample")
    XCTAssertLessThan(snapshot.range?.lowerBound ?? .infinity, oldest.timestamp.timeIntervalSince1970)
    XCTAssertGreaterThan(snapshot.range?.upperBound ?? -.infinity, newest.timestamp.timeIntervalSince1970)
  }

  func testPanningReloadsOnlyTheRequestedContinuousWindow() async throws {
    let clock = try makeSeedClock()
    let newest = try await insert(at: try clock.instant(daysAgo: 0), text: "newest day")
    let middle = try await insert(at: try clock.instant(daysAgo: 2), text: "middle day")
    let oldest = try await insert(at: try clock.instant(daysAgo: 9), text: "oldest day")
    let viewModel = await MainActor.run { RewindViewModel() }
    await viewModel.surveyCapturedHistory(attempts: 1)

    await viewModel.loadTimelineWindow(
      from: middle.timestamp.addingTimeInterval(-3600).timeIntervalSince1970,
      to: middle.timestamp.addingTimeInterval(3600).timeIntervalSince1970)
    var text = await MainActor.run { viewModel.screenshots.compactMap(\.ocrText) }
    XCTAssertEqual(text, ["middle day"])

    await viewModel.loadTimelineWindow(
      from: oldest.timestamp.addingTimeInterval(-3600).timeIntervalSince1970,
      to: oldest.timestamp.addingTimeInterval(3600).timeIntervalSince1970)
    text = await MainActor.run { viewModel.screenshots.compactMap(\.ocrText) }
    XCTAssertEqual(text, ["oldest day"], "panning back must query the older viewport without a day transition")

    await viewModel.loadTimelineWindow(
      from: newest.timestamp.addingTimeInterval(-3600).timeIntervalSince1970,
      to: newest.timestamp.addingTimeInterval(3600).timeIntervalSince1970)
    text = await MainActor.run { viewModel.screenshots.compactMap(\.ocrText) }
    XCTAssertEqual(text, ["newest day"])
  }

  func testTimelineLoadCannotReplaceSearchResultsThatStartWhileItsQueryIsInFlight() async throws {
    let queryStarted = expectation(description: "timeline query started")
    let releaseQuery = AsyncStream<Void>.makeStream()
    let staleTimelineFrame = Screenshot(
      timestamp: Date(timeIntervalSince1970: 200), appName: "Timeline", imagePath: "timeline.jpg")
    let searchFrame = Screenshot(
      timestamp: Date(timeIntervalSince1970: 300), appName: "Search", imagePath: "search.jpg")
    let viewModel = await MainActor.run {
      RewindViewModel { _, _, _, _ in
        queryStarted.fulfill()
        for await _ in releaseQuery.stream { break }
        return [staleTimelineFrame]
      }
    }

    let load = Task {
      await viewModel.loadTimelineWindow(from: 100, to: 400)
    }
    await fulfillment(of: [queryStarted])
    await MainActor.run {
      viewModel.activeSearchQuery = "needle"
      viewModel.screenshots = [searchFrame]
    }
    releaseQuery.continuation.yield()
    await load.value

    let visible = await MainActor.run { viewModel.screenshots }
    XCTAssertEqual(visible, [searchFrame], "an older timeline read must not overwrite the active search source")
  }

  func testAppFilterIsAppliedBeforeTimelineSampling() async throws {
    let now = Date()
    for offset in 0..<12 {
      _ = try await RewindDatabase.shared.insertScreenshot(
        Screenshot(
          timestamp: now.addingTimeInterval(Double(offset)),
          appName: "BusyApp",
          videoChunkPath: "busy/\(offset).mp4",
          frameOffset: 0,
          ocrText: "busy \(offset)",
          isIndexed: true))
    }
    for offset in 0..<3 {
      _ = try await RewindDatabase.shared.insertScreenshot(
        Screenshot(
          timestamp: now.addingTimeInterval(Double(offset) + 0.5),
          appName: "SparseApp",
          videoChunkPath: "sparse/\(offset).mp4",
          frameOffset: 0,
          ocrText: "sparse \(offset)",
          isIndexed: true))
    }

    let sample = try await RewindDatabase.shared.getScreenshotsSampled(
      from: now.addingTimeInterval(-1),
      to: now.addingTimeInterval(20),
      targetCount: 3,
      appFilter: "SparseApp")

    XCTAssertEqual(sample.count, 3)
    XCTAssertTrue(sample.allSatisfy { $0.appName == "SparseApp" })
  }

  func testBoundedAllTimeSampleIncludesTheOldestAndNewestCapture() async throws {
    let clock = try makeSeedClock()
    for offset in (0..<10).reversed() {
      try await insert(at: try clock.instant(daysAgo: offset), text: "day \(offset)")
    }
    let start = try clock.dayStart(daysAgo: 10)
    let end = try clock.instant(daysAgo: -1)

    let sample = try await RewindDatabase.shared.getScreenshotsSampled(
      from: start, to: end, targetCount: 3)

    XCTAssertEqual(sample.count, 3)
    XCTAssertEqual(sample.first?.ocrText, "day 9", "the all-time range must retain its oldest end")
    XCTAssertEqual(sample.last?.ocrText, "day 0", "the all-time range must retain its live/newest end")
  }
}
