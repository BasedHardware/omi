import XCTest

@testable import Omi_Computer

/// Regression test for the retention data-loss bug: the screenshot sweep
/// (`deleteScreenshotsOlderThan`, driven by the "how long to keep screen
/// recordings" setting, default 7 days) also deleted `observations` and
/// synced `transcription_sessions`, destroying conversation transcripts on the
/// first launch after upgrade. Transcripts now age out on their own, much
/// longer window.
final class RewindTranscriptRetentionTests: XCTestCase {

  private var testUserId: String!
  private var savedTranscriptRetentionDays: Int = 90

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "transcript-retention-test-\(UUID().uuidString)"
    RewindDatabase.currentUserId = testUserId
    try await RewindDatabase.shared.initialize()
    savedTranscriptRetentionDays = RewindSettings.shared.transcriptRetentionDays
  }

  override func tearDown() async throws {
    RewindSettings.shared.transcriptRetentionDays = savedTranscriptRetentionDays
    RewindDatabase.currentUserId = nil
    try await super.tearDown()
  }

  func testTranscriptRetentionDefaultsToNinetyDaysAndIsIndependentOfScreenshotRetention() {
    XCTAssertEqual(
      RewindSettings.defaultTranscriptRetentionDays, 90,
      "transcripts must default to a much longer window than screen recordings")

    let settings = RewindSettings.shared
    let savedRetentionDays = settings.retentionDays
    defer { settings.retentionDays = savedRetentionDays }

    settings.transcriptRetentionDays = 180
    settings.retentionDays = 3
    XCTAssertEqual(
      settings.transcriptRetentionDays, 180,
      "shortening the screen-recording window must not change transcript retention")
    XCTAssertEqual(
      UserDefaults.standard.object(forKey: "rewindTranscriptRetentionDays") as? Int, 180,
      "transcript retention must persist under its own key")
  }

  func testScreenshotSweepKeepsObservationsAndTranscriptSweepRemovesThem() async throws {
    let thirtyDaysAgo = Calendar.current.date(byAdding: .day, value: -30, to: Date())!

    _ = try await ActionItemStorage.shared.insertObservation(
      ObservationRecord(
        screenshotId: nil,
        appName: "RetentionTest",
        contextSummary: "summary",
        currentActivity: "activity",
        hasTask: false,
        createdAt: thirtyDaysAgo),
      authorization: .unrestricted)

    // The screenshot sweep runs with the short screen-recording cutoff; it must
    // leave the 30-day-old observation alone.
    _ = try await RewindDatabase.shared.deleteScreenshotsOlderThan(Date())

    let withinTranscriptWindow = Calendar.current.date(byAdding: .day, value: -90, to: Date())!
    let untouched = try await RewindDatabase.shared.deleteTranscriptsAndObservationsOlderThan(
      withinTranscriptWindow)
    XCTAssertEqual(
      untouched.observations, 0,
      "an observation inside the transcript retention window must survive both sweeps")

    let removed = try await RewindDatabase.shared.deleteTranscriptsAndObservationsOlderThan(Date())
    XCTAssertEqual(
      removed.observations, 1,
      "the transcript sweep must remove observations older than its own cutoff")
  }
}
