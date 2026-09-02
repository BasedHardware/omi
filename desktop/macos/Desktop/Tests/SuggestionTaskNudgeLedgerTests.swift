import XCTest

@testable import Omi_Computer

final class SuggestionTaskNudgeLedgerTests: XCTestCase {

  func testFreshnessWindowIsTwoDaysThroughEndOfToday() throws {
    let calendar = Calendar(identifier: .gregorian)
    let now = try XCTUnwrap(calendar.date(from: DateComponents(year: 2026, month: 9, day: 2, hour: 15)))
    XCTAssertTrue(
      SuggestionTaskNudgePolicy.isDueFresh(
        calendar.date(byAdding: .day, value: -1, to: now), now: now, calendar: calendar))
    XCTAssertTrue(
      SuggestionTaskNudgePolicy.isDueFresh(
        calendar.date(byAdding: .day, value: -2, to: now), now: now, calendar: calendar))
    XCTAssertFalse(
      SuggestionTaskNudgePolicy.isDueFresh(
        calendar.date(byAdding: .day, value: -3, to: now), now: now, calendar: calendar))
    XCTAssertFalse(SuggestionTaskNudgePolicy.isDueFresh(nil, now: now, calendar: calendar))
  }

  func testDeliveryBackoffThenPermanentUntilUpdate() {
    var ledger = SuggestionTaskNudgeLedger()
    let now = Date(timeIntervalSince1970: 1_000_000)
    SuggestionTaskNudgePolicy.recordingDelivery(taskId: "t1", in: &ledger, now: now)
    XCTAssertEqual(
      ledger.records["t1"]?.suppressedUntil,
      now.addingTimeInterval(4 * 60 * 60))
    SuggestionTaskNudgePolicy.recordingDelivery(
      taskId: "t1", in: &ledger, now: now.addingTimeInterval(5 * 60 * 60))
    XCTAssertEqual(
      ledger.records["t1"]?.suppressedUntil,
      now.addingTimeInterval(5 * 60 * 60 + 24 * 60 * 60))
    SuggestionTaskNudgePolicy.recordingDelivery(
      taskId: "t1", in: &ledger, now: now.addingTimeInterval(30 * 60 * 60))
    XCTAssertEqual(ledger.records["t1"]?.suppressedUntil, .distantFuture)
  }

  func testEngagementSuppressesForSevenDays() {
    var ledger = SuggestionTaskNudgeLedger()
    let now = Date(timeIntervalSince1970: 2_000_000)
    SuggestionTaskNudgePolicy.recordingEngagement(taskId: "john", in: &ledger, now: now)
    XCTAssertEqual(
      ledger.records["john"]?.suppressedUntil,
      now.addingTimeInterval(7 * 24 * 60 * 60))
    XCTAssertFalse(
      SuggestionTaskNudgePolicy.isEligible(
        taskId: "john", dueAt: now, ledger: ledger, now: now.addingTimeInterval(6 * 24 * 60 * 60)))
    XCTAssertTrue(
      SuggestionTaskNudgePolicy.isEligible(
        taskId: "john", dueAt: now.addingTimeInterval(7 * 24 * 60 * 60), ledger: ledger,
        now: now.addingTimeInterval(7 * 24 * 60 * 60)))
  }

  func testTaskIdParsesFromNotificationDetail() {
    XCTAssertEqual(
      SuggestionTaskNudgePolicy.taskId(fromNotificationDetail: "task_id=abc-123\nFollow up with John"),
      "abc-123")
    XCTAssertNil(SuggestionTaskNudgePolicy.taskId(fromNotificationDetail: "Follow up with John"))
  }

  func testReplayJohnNudgesStopAfterFirstDeliveryAndEngagement() {
    var ledger = SuggestionTaskNudgeLedger()
    let now = Date(timeIntervalSince1970: 3_000_000)
    let due = now
    XCTAssertTrue(SuggestionTaskNudgePolicy.isEligible(taskId: "john", dueAt: due, ledger: ledger, now: now))
    SuggestionTaskNudgePolicy.recordingDelivery(taskId: "john", in: &ledger, now: now)
    XCTAssertFalse(
      SuggestionTaskNudgePolicy.isEligible(
        taskId: "john", dueAt: due, ledger: ledger, now: now.addingTimeInterval(60)))
    SuggestionTaskNudgePolicy.recordingEngagement(
      taskId: "john", in: &ledger, now: now.addingTimeInterval(120))
    XCTAssertFalse(
      SuggestionTaskNudgePolicy.isEligible(
        taskId: "john", dueAt: due, ledger: ledger, now: now.addingTimeInterval(24 * 60 * 60)))
  }
}
