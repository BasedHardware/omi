import XCTest

@testable import Omi_Computer

/// Regression coverage for the recurring-task investigation dedup gate.
///
/// `getDueRecurringTasks` returns every incomplete recurring task with
/// `dueAt <= now` and nothing advances `dueAt`, so before this gate every due
/// task re-fired a fresh agent investigation on each 60s scheduler tick,
/// forever. The gate allows one investigation per 4 hours, keyed on
/// `agentStartedAt` (stamped by `investigateInBackground` before sending).
@MainActor
final class RecurringTaskSchedulerGateTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    func testNeverInvestigatedTaskIsInvestigated() {
        XCTAssertTrue(RecurringTaskScheduler.shouldInvestigate(lastInvestigatedAt: nil, now: now))
    }

    func testRecentInvestigationIsSkipped() {
        let oneMinuteAgo = now.addingTimeInterval(-60)
        XCTAssertFalse(RecurringTaskScheduler.shouldInvestigate(lastInvestigatedAt: oneMinuteAgo, now: now))
    }

    func testJustUnderFourHoursIsStillSkipped() {
        let underFourHours = now.addingTimeInterval(-4 * 3600 + 1)
        XCTAssertFalse(RecurringTaskScheduler.shouldInvestigate(lastInvestigatedAt: underFourHours, now: now))
    }

    func testOverFourHoursIsReinvestigated() {
        let overFourHours = now.addingTimeInterval(-4 * 3600 - 1)
        XCTAssertTrue(RecurringTaskScheduler.shouldInvestigate(lastInvestigatedAt: overFourHours, now: now))
    }
}
