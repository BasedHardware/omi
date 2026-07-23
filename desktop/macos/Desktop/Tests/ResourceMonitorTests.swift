import Foundation
import XCTest

@testable import Omi_Computer

/// Regression coverage for `MemoryPressureEpisodeTracker`. The `.extreme` level
/// (>= 3 GB) is more severe than `.critical`, but the decision guard previously
/// matched only `.critical`, so the worst level silently returned
/// shouldReportCritical=false / shouldRemediate=false and fell to a low-severity
/// path with no remediation.
final class ResourceMonitorTests: XCTestCase {
  private let epoch = Date(timeIntervalSince1970: 0)

  func testExtremeLevelReportsAndRemediatesLikeCritical() {
    var tracker = MemoryPressureEpisodeTracker()
    let decision = tracker.evaluate(memoryFootprintMB: 3200, at: epoch)
    XCTAssertEqual(decision.level, .extreme)
    XCTAssertTrue(decision.shouldReportCritical, "extreme is the worst level; it must report")
    XCTAssertTrue(decision.shouldRemediate, "extreme must remediate")
  }

  func testCriticalReportsButWarningDoesNot() {
    var tracker = MemoryPressureEpisodeTracker()
    let warning = tracker.evaluate(memoryFootprintMB: 600, at: epoch)
    XCTAssertEqual(warning.level, .warning)
    XCTAssertFalse(warning.shouldReportCritical)
    XCTAssertFalse(warning.shouldRemediate)

    let critical = tracker.evaluate(memoryFootprintMB: 900, at: epoch)
    XCTAssertEqual(critical.level, .critical)
    XCTAssertTrue(critical.shouldReportCritical)
    XCTAssertTrue(critical.shouldRemediate)
  }
}
