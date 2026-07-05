import XCTest

@testable import Omi_Computer

/// Verifies the resume-on-paywall-clear decision used by
/// `AppState.fetchTrialMetadata()`: screen-analysis monitoring restarts
/// exactly when a trial fetch transitions the paywall from set to clear and
/// the user still wants (and can run) screen analysis.
final class PaywallClearResumeTests: XCTestCase {

    func testResumesWhenFetchClearsPaywallAndAllConditionsHold() {
        XCTAssertTrue(
            AppState.shouldResumeMonitoringAfterPaywallClear(
                wasPaywalled: true, isPaywalledNow: false,
                screenAnalysisEnabled: true, isMonitoring: false, keysAvailable: true
            )
        )
    }

    func testDoesNotResumeWhenPaywallWasNeverSet() {
        // Ordinary fetch on a healthy account — no transition, no restart.
        XCTAssertFalse(
            AppState.shouldResumeMonitoringAfterPaywallClear(
                wasPaywalled: false, isPaywalledNow: false,
                screenAnalysisEnabled: true, isMonitoring: false, keysAvailable: true
            )
        )
    }

    func testDoesNotResumeWhileStillPaywalled() {
        // Genuinely expired account: flag stays set, capture stays stopped.
        XCTAssertFalse(
            AppState.shouldResumeMonitoringAfterPaywallClear(
                wasPaywalled: true, isPaywalledNow: true,
                screenAnalysisEnabled: true, isMonitoring: false, keysAvailable: true
            )
        )
    }

    func testDoesNotResumeWhenScreenAnalysisDisabled() {
        XCTAssertFalse(
            AppState.shouldResumeMonitoringAfterPaywallClear(
                wasPaywalled: true, isPaywalledNow: false,
                screenAnalysisEnabled: false, isMonitoring: false, keysAvailable: true
            )
        )
    }

    func testDoesNotResumeWhenAlreadyMonitoring() {
        XCTAssertFalse(
            AppState.shouldResumeMonitoringAfterPaywallClear(
                wasPaywalled: true, isPaywalledNow: false,
                screenAnalysisEnabled: true, isMonitoring: true, keysAvailable: true
            )
        )
    }

    func testDoesNotResumeBeforeAPIKeysLoad() {
        // The key-load retry path in DesktopHomeView covers this case instead.
        XCTAssertFalse(
            AppState.shouldResumeMonitoringAfterPaywallClear(
                wasPaywalled: true, isPaywalledNow: false,
                screenAnalysisEnabled: true, isMonitoring: false, keysAvailable: false
            )
        )
    }
}
