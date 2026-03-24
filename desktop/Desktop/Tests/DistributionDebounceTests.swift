import XCTest
@testable import Omi_Computer

final class DistributionDebounceTests: XCTestCase {

    // MARK: - ContextDetection.didContextChange tests (core gate logic)

    func testContextChangeDetectedOnAppSwitch() {
        XCTAssertTrue(ContextDetection.didContextChange(
            fromApp: "Safari", fromWindowTitle: "Google",
            toApp: "Xcode", toWindowTitle: "Project"
        ))
    }

    func testContextChangeDetectedOnWindowTitleChange() {
        XCTAssertTrue(ContextDetection.didContextChange(
            fromApp: "Safari", fromWindowTitle: "Google",
            toApp: "Safari", toWindowTitle: "GitHub"
        ))
    }

    func testNoContextChangeForSameAppAndTitle() {
        XCTAssertFalse(ContextDetection.didContextChange(
            fromApp: "Safari", fromWindowTitle: "Google",
            toApp: "Safari", toWindowTitle: "Google"
        ))
    }

    func testContextChangeFromNilApp() {
        // First frame: nil -> app should detect change (triggers immediate distribution)
        XCTAssertTrue(ContextDetection.didContextChange(
            fromApp: nil, fromWindowTitle: nil,
            toApp: "Safari", toWindowTitle: "Google"
        ))
    }

    func testNoContextChangeForSpinnerOnlyDifference() {
        // Spinner characters should be normalized away
        XCTAssertFalse(ContextDetection.didContextChange(
            fromApp: "Terminal", fromWindowTitle: "build ⠋",
            toApp: "Terminal", toWindowTitle: "build ⠙"
        ))
    }

    func testNoContextChangeForTimerOnlyDifference() {
        // Timer patterns should be normalized away
        XCTAssertFalse(ContextDetection.didContextChange(
            fromApp: "Toggl", fromWindowTitle: "Task 12:34",
            toApp: "Toggl", toWindowTitle: "Task 15:20"
        ))
    }

    func testNoContextChangeForNotificationCountDifference() {
        // Notification counts like (2) should be normalized away
        XCTAssertFalse(ContextDetection.didContextChange(
            fromApp: "Slack", fromWindowTitle: "Slack (2)",
            toApp: "Slack", toWindowTitle: "Slack (5)"
        ))
    }

    func testContextChangeForRealTitleChange() {
        // Real title changes should be detected even with noise
        XCTAssertTrue(ContextDetection.didContextChange(
            fromApp: "Safari", fromWindowTitle: "Google (2)",
            toApp: "Safari", toWindowTitle: "GitHub (3)"
        ))
    }
}
