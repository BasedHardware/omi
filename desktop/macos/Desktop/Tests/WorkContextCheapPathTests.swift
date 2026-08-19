import GRDB
import XCTest

@testable import Omi_Computer

/// End-to-end shape of `get_work_context` against a real migrated Rewind profile.
///
/// The point of these tests is the *default* call: a question like "where was that pricing
/// doc" must be answered from the durable handle index, without a Rewind frame decode and
/// without Screen Recording. Tape stays reachable, but only when the caller asks for it.
final class WorkContextCheapPathTests: XCTestCase {
  private var testUserId = ""
  private var userDir: URL?

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "work-context-cheap-path-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let appSupport = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first)
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    try await super.tearDown()
  }

  func testDefaultCallAnswersFromHandlesWithoutTape() async throws {
    let url = try await seedVisit()

    let payload = await ScreenContextWorkContextBuilder.payload(arguments: [:])

    XCTAssertEqual(payload["ok"] as? Bool, true)
    let visits = try XCTUnwrap(payload["visits"] as? [[String: Any]], "default call must return visits")
    let handles = try XCTUnwrap(visits.first?["handles"] as? [[String: Any]])
    XCTAssertEqual(handles.first?["value"] as? String, url.value)

    // The tape half must not have been built: no timeline runs, no screenshot_id, and
    // above all no `image_bytes`, which is the field whose only cost is a video-chunk
    // decode plus a full-quality JPEG re-encode of a frame nothing ever reads.
    XCTAssertEqual((payload["timeline"] as? [[String: Any]])?.count, 0)
    let screenNow = try XCTUnwrap(payload["screen_now"] as? [String: Any])
    XCTAssertEqual(screenNow["available"] as? Bool, false)
    XCTAssertNil(screenNow["screenshot_id"])
    XCTAssertNil(screenNow["image_bytes"])
    XCTAssertNil(screenNow["ocr_preview"])

    let guidance = try XCTUnwrap(payload["guidance"] as? String)
    XCTAssertTrue(guidance.contains("handles"), "guidance must point at handles: \(guidance)")
  }

  /// Screen Recording gates pixels. It must not gate the answer to "where was that doc",
  /// which is why the index read happens before the permission check.
  func testHandlesSurviveWhenScreenRecordingIsUnavailable() async throws {
    let url = try await seedVisit()

    // include_screen forces the tape branch, which is where the permission guard lives.
    let payload = await ScreenContextWorkContextBuilder.payload(arguments: ["include_screen": true])

    let visits = try XCTUnwrap(
      payload["visits"] as? [[String: Any]],
      "visits must ride along even when the screen half fails or is denied")
    let handles = try XCTUnwrap(visits.first?["handles"] as? [[String: Any]])
    XCTAssertEqual(handles.first?["value"] as? String, url.value)
  }

  /// "You last worked in Claude 2 hours ago", asked while Claude was on screen.
  ///
  /// The visit times are wall-clock strings, and this path used to emit no absolute timestamp
  /// at all, so nothing in the payload said what "now" was. The only ISO timestamp left was
  /// `briefs[].last_visit`, which pushed the reader onto bucket recency instead of the visit
  /// actually in progress.
  func testPayloadIsTemporallyAnchored() async throws {
    try await seedVisit()

    let payload = await ScreenContextWorkContextBuilder.payload(arguments: [:])

    let generatedAt = try XCTUnwrap(
      payload["generated_at"] as? String, "payload must say when it was produced")
    XCTAssertNotNil(
      ISO8601DateFormatter().date(from: generatedAt), "generated_at must be an absolute instant")

    let visits = try XCTUnwrap(payload["visits"] as? [[String: Any]])
    let visit = try XCTUnwrap(visits.first)
    let minutesAgo = try XCTUnwrap(
      visit["minutes_ago"] as? Int, "a visit must say how long ago it was, not only when")
    // The fixture visit ended 60s before now, so this is the current minute or the one before it.
    XCTAssertLessThanOrEqual(minutesAgo, 2)
    XCTAssertGreaterThanOrEqual(minutesAgo, 0)
    XCTAssertNotNil(visit["start"], "the readable wall-clock form stays")
    XCTAssertNil(visit["start_at"], "an ISO pair per visit costs ~50 tokens to say what one int says")
  }

  /// A visit still in progress is the answer to "what am I in right now", so it must not look
  /// like one that ended the instant it began.
  func testOngoingVisitSaysSo() throws {
    let url = try XCTUnwrap(WorkHistoryHandle.url("https://docs.google.com/spreadsheets/d/x/edit"))
    let started = Date().addingTimeInterval(-60)
    let open = WorkHistoryVisitRecord(
      startedAt: started, endedAt: nil, appName: "Google Chrome", title: "Q3 pricing",
      handles: [url], bucketID: nil, outcome: "active")
    let json = open.jsonObject(clock: { _ in "15:25" }, now: Date())
    XCTAssertEqual(json["ongoing"] as? Bool, true)

    let closed = WorkHistoryVisitRecord(
      startedAt: started, endedAt: started.addingTimeInterval(30), appName: "Google Chrome",
      title: "Q3 pricing", handles: [url], bucketID: nil, outcome: "completed")
    XCTAssertNil(closed.jsonObject(clock: { _ in "15:25" }, now: Date())["ongoing"])
  }

  /// A visit whose only handle is the `app_window` fallback names nothing openable — it
  /// carries the same app and title the timeline already shows. Suppressing the tape for it
  /// would drop evidence and return no address in exchange, so the tool must fall through.
  /// This is the observed state on a real profile with Accessibility ungranted.
  func testAppWindowOnlyHandlesDoNotSuppressTheTimeline() async throws {
    let started = Date().addingTimeInterval(-120)
    let pool = await RewindDatabase.shared.getDatabaseQueue()
    let queue = try XCTUnwrap(pool)
    let fallback = try XCTUnwrap(
      WorkHistoryHandle.appWindow(appName: "Google Chrome", title: "Q3 pricing model"))
    XCTAssertFalse(fallback.isDurable, "app_window must not count as an address")
    try await queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (contextGeneration, poolEpoch, appName, rawContextKey, normalizedContextKey,
             referenceHash, startedAt, endedAt, outcome, handlesJson, createdAt, updatedAt)
          VALUES (1, 1, 'Google Chrome', 'Google Chrome\nQ3 pricing model', 'chrome::q3',
                  'hash-fallback', ?, ?, 'completed', ?, ?, ?)
          """,
        arguments: [
          started, started.addingTimeInterval(60),
          WorkHistoryHandle.encodeList([fallback]), started, started,
        ])
    }

    let payload = await ScreenContextWorkContextBuilder.payload(arguments: [:])
    let screenNow = payload["screen_now"] as? [String: Any]
    XCTAssertNotEqual(
      screenNow?["reason"] as? String, "not_requested",
      "an app_window-only index must not take the cheap path")
  }

  /// A profile with no visits must fall through to exactly today's behavior rather than
  /// returning an empty answer.
  func testEmptyIndexFallsThroughToExistingPath() async throws {
    let payload = await ScreenContextWorkContextBuilder.payload(arguments: [:])
    XCTAssertNil(payload["visits"])
    XCTAssertNotNil(payload["screen_now"], "fallback path must still produce a screen_now envelope")
  }

  @discardableResult
  private func seedVisit() async throws -> WorkHistoryHandle {
    let url = try XCTUnwrap(WorkHistoryHandle.url("https://docs.google.com/spreadsheets/d/pricing/edit"))
    let started = Date().addingTimeInterval(-120)
    let pool = await RewindDatabase.shared.getDatabaseQueue()
    let queue = try XCTUnwrap(pool)
    try await queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO context_buckets
            (id, subjectKind, subjectID, displayLabel, visitCount, lastVisitedAt, createdAt, updatedAt)
          VALUES ('bucket-pricing', 'url', ?, 'Q3 pricing model', 1, ?, ?, ?)
          """,
        arguments: [url.value, started, started, started])
      try db.execute(
        sql: """
          INSERT INTO context_visits
            (contextGeneration, poolEpoch, bucketID, appName, rawContextKey, normalizedContextKey,
             referenceHash, startedAt, endedAt, outcome, handlesJson, createdAt, updatedAt)
          VALUES (1, 1, 'bucket-pricing', 'Google Chrome', 'Google Chrome\nQ3 pricing model',
                  'chrome::q3-pricing', ?, ?, ?, 'completed', ?, ?, ?)
          """,
        arguments: [
          url.identityKey, started, started.addingTimeInterval(60),
          WorkHistoryHandle.encodeList([url]), started, started,
        ])
    }
    return url
  }
}
