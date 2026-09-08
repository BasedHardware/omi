import Foundation
import XCTest

@testable import Omi_Computer

final class MemoryPressureEpisodeTrackerTests: XCTestCase {
  func testCriticalEpisodeSeparatesRemediationCadenceFromSentryReminderCadence() {
    var tracker = MemoryPressureEpisodeTracker()
    let startedAt = Date(timeIntervalSince1970: 1_000)

    let entered = tracker.evaluate(memoryFootprintMB: 900, at: startedAt)
    XCTAssertEqual(entered.level, .critical)
    XCTAssertEqual(entered.reportPhase, "entered")
    XCTAssertTrue(entered.shouldReportCritical)
    XCTAssertTrue(entered.shouldRemediate)

    let stillPressured = tracker.evaluate(
      memoryFootprintMB: 950,
      at: startedAt.addingTimeInterval(5 * 60))
    XCTAssertEqual(stillPressured.reportPhase, "sustained")
    XCTAssertFalse(stillPressured.shouldReportCritical)
    XCTAssertTrue(stillPressured.shouldRemediate)

    let sustainedReminder = tracker.evaluate(
      memoryFootprintMB: 1_000,
      at: startedAt.addingTimeInterval(15 * 60))
    XCTAssertTrue(sustainedReminder.shouldReportCritical)
    XCTAssertTrue(sustainedReminder.shouldRemediate)
  }

  func testCriticalEpisodeUsesHysteresisAndReportsAgainOnlyAfterRecovery() {
    var tracker = MemoryPressureEpisodeTracker()
    let startedAt = Date(timeIntervalSince1970: 2_000)

    _ = tracker.evaluate(memoryFootprintMB: 850, at: startedAt)

    let thresholdJitter = tracker.evaluate(
      memoryFootprintMB: 799,
      at: startedAt.addingTimeInterval(30))
    XCTAssertEqual(thresholdJitter.level, .critical)
    XCTAssertFalse(thresholdJitter.shouldReportCritical)

    let recovered = tracker.evaluate(
      memoryFootprintMB: 719,
      at: startedAt.addingTimeInterval(60))
    XCTAssertEqual(recovered.level, .warning)

    let newEpisode = tracker.evaluate(
      memoryFootprintMB: 800,
      at: startedAt.addingTimeInterval(90))
    XCTAssertEqual(newEpisode.reportPhase, "entered")
    XCTAssertTrue(newEpisode.shouldReportCritical)
    XCTAssertTrue(newEpisode.shouldRemediate)
  }

  func testWarningRecoveryAlsoUsesHysteresis() {
    var tracker = MemoryPressureEpisodeTracker()
    let startedAt = Date(timeIntervalSince1970: 3_000)

    XCTAssertEqual(
      tracker.evaluate(memoryFootprintMB: 550, at: startedAt).level,
      .warning)
    XCTAssertEqual(
      tracker.evaluate(memoryFootprintMB: 499, at: startedAt.addingTimeInterval(30)).level,
      .warning)
    XCTAssertEqual(
      tracker.evaluate(memoryFootprintMB: 449, at: startedAt.addingTimeInterval(60)).level,
      .nominal)
  }

  func testExtremeEntryDoesNotDuplicateCriticalReportingOrRemediation() {
    var tracker = MemoryPressureEpisodeTracker()
    let decision = tracker.evaluate(
      memoryFootprintMB: tracker.extremeThresholdMB,
      at: Date(timeIntervalSince1970: 4_000))

    XCTAssertEqual(decision.previousLevel, .nominal)
    XCTAssertEqual(decision.level, .extreme)
    XCTAssertFalse(decision.shouldReportCritical)
    XCTAssertFalse(decision.shouldRemediate)
  }

  func testExtremeToCriticalRemainsOneSustainedPressureEpisode() {
    var tracker = MemoryPressureEpisodeTracker()
    let startedAt = Date(timeIntervalSince1970: 5_000)

    _ = tracker.evaluate(memoryFootprintMB: 900, at: startedAt)
    let extreme = tracker.evaluate(
      memoryFootprintMB: tracker.extremeThresholdMB,
      at: startedAt.addingTimeInterval(30))
    let backToCritical = tracker.evaluate(
      memoryFootprintMB: 900,
      at: startedAt.addingTimeInterval(60))

    XCTAssertEqual(extreme.level, .extreme)
    XCTAssertEqual(backToCritical.previousLevel, .extreme)
    XCTAssertEqual(backToCritical.level, .critical)
    XCTAssertEqual(backToCritical.reportPhase, "sustained")
    XCTAssertFalse(backToCritical.shouldReportCritical)
    XCTAssertFalse(backToCritical.shouldRemediate)
  }

  func testExtremeRecoveryClearsEpisodeBeforeNextCriticalEntry() {
    var tracker = MemoryPressureEpisodeTracker()
    let startedAt = Date(timeIntervalSince1970: 6_000)

    _ = tracker.evaluate(
      memoryFootprintMB: tracker.extremeThresholdMB,
      at: startedAt)
    let recovered = tracker.evaluate(
      memoryFootprintMB: tracker.warningRecoveryMB - 1,
      at: startedAt.addingTimeInterval(30))
    let nextCritical = tracker.evaluate(
      memoryFootprintMB: tracker.criticalThresholdMB,
      at: startedAt.addingTimeInterval(60))

    XCTAssertEqual(recovered.level, .nominal)
    XCTAssertEqual(nextCritical.reportPhase, "entered")
    XCTAssertTrue(nextCritical.shouldReportCritical)
    XCTAssertTrue(nextCritical.shouldRemediate)
  }
}
