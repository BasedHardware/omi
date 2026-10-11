import XCTest

@testable import Omi_Computer

@MainActor
final class ProactivityReceiptStoreTests: XCTestCase {
  private func withJournal(_ body: (URL) throws -> Void) throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    try body(directory.appendingPathComponent("receipts.json"))
  }
  private func request(_ action: String) -> OmiAPI.ProactivityOutcomeRequest {
    .init(action: action, channel: "feed", eventId: "event-\(action)", surface: "macos")
  }
  func testShownReceiptAndOutboxSurviveRelaunchAndDedupeFeedPush() throws {
    try withJournal { url in
      let first = try ProactivityReceiptStore(url: url, ownerID: "a")
      XCTAssertFalse(first.hasShown("item"))
      try first.record(itemID: "item", request: request("shown"))
      let relaunched = try ProactivityReceiptStore(url: url, ownerID: "a")
      try relaunched.record(itemID: "item", request: request("shown"))
      XCTAssertTrue(relaunched.hasShown("item"))
      XCTAssertEqual(relaunched.pending.count, 1)
      try relaunched.acknowledge("event-shown")
      XCTAssertTrue(try ProactivityReceiptStore(url: url, ownerID: "a").hasShown("item"))
      XCTAssertTrue(relaunched.pending.isEmpty)
    }
  }
  func testTimeoutIsNotAShownReceiptOrAnOutcome() throws {
    try withJournal { url in
      let store = try ProactivityReceiptStore(url: url, ownerID: "a")
      try store.record(itemID: "item", request: request("timeout"))
      XCTAssertFalse(store.hasShown("item"))
      XCTAssertTrue(store.pending.isEmpty)
    }
  }
  func testOwnerSwitchAndSignoutPurgeJournal() throws {
    try withJournal { url in
      let a = try ProactivityReceiptStore(url: url, ownerID: "a")
      try a.record(itemID: "item", request: request("shown"))
      let b = try ProactivityReceiptStore(url: url, ownerID: "b")
      XCTAssertFalse(b.hasShown("item"))
      XCTAssertTrue(b.pending.isEmpty)
      try b.purge()
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }
  }
  func testFailedDeliveryRemainsRetryableWithIdenticalEventID() throws {
    try withJournal { url in
      let store = try ProactivityReceiptStore(url: url, ownerID: "a")
      try store.record(itemID: "item", request: request("opened"))
      // Network failure does not acknowledge; the next process sends the same event.
      let retry = try ProactivityReceiptStore(url: url, ownerID: "a")
      XCTAssertEqual(retry.pending.first?.request.eventId, "event-opened")
      try retry.acknowledge("event-opened")
      XCTAssertTrue(try ProactivityReceiptStore(url: url, ownerID: "a").pending.isEmpty)
    }
  }
  func testOutboxRetriesAfterTransportFailureAndFencesOwnerChange() async throws {
    enum Offline: Error { case offline }
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let url = directory.appendingPathComponent("receipts.json")
    let store = try ProactivityReceiptStore(url: url, ownerID: "a")
    try store.record(itemID: "item", request: request("shown"))
    var attempts = [String]()
    do {
      try await store.drain(isCurrent: { true }) { entry in
        attempts.append(entry.request.eventId)
        throw Offline.offline
      }
      XCTFail("transport failure must retain the outbox")
    } catch Offline.offline {}
    XCTAssertEqual(store.pending.count, 1)
    try await store.drain(isCurrent: { false }) { _ in XCTFail("foreign owner must never send") }
    let restarted = try ProactivityReceiptStore(url: url, ownerID: "a")
    try await restarted.drain(isCurrent: { true }) { attempts.append($0.request.eventId) }
    XCTAssertEqual(attempts, ["event-shown", "event-shown"])
    XCTAssertTrue(restarted.pending.isEmpty)
  }

  func testColdSignOutPurgesJournalBeforeConsumerEverStarts() throws {
    try withJournal { url in
      let previousProcess = try ProactivityReceiptStore(url: url, ownerID: "a")
      try previousProcess.record(itemID: "item", request: request("shown"))
      let coldConsumer = ProactivityFeedConsumer(journalURL: url)
      coldConsumer.purgeForOwnerTransition()
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      let nextSession = try ProactivityReceiptStore(url: url, ownerID: "a")
      XCTAssertFalse(nextSession.hasShown("item"))
      XCTAssertTrue(nextSession.pending.isEmpty)
    }
  }

  func testExpiryUsesServerClockAndRejectsMalformedOrFutureCreation() {
    let now = Date(timeIntervalSince1970: 1000)
    XCTAssertEqual(
      ProactivityFreshness.deadline(createdAt: "2026-10-03T12:00:00Z", serverTime: "2026-10-04T12:00:00Z", now: now),
      now)
    XCTAssertNil(ProactivityFreshness.deadline(createdAt: "invalid", serverTime: "2026-10-03T12:00:00Z"))
    XCTAssertNil(ProactivityFreshness.deadline(createdAt: "2026-10-04T12:00:00Z", serverTime: "2026-10-03T12:00:00Z"))
  }
}
