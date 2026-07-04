import XCTest

final class DashboardCaptureStateTests: XCTestCase {
    func testDashboardCaptureStatusUsesLiveMonitoringState() throws {
        let source = try dashboardSource()

        XCTAssertTrue(
            source.contains("private var isCaptureLive: Bool"),
            "DashboardPage should centralize live capture state so the header reflects the running monitor"
        )
        XCTAssertTrue(
            source.contains("if isCaptureLive {\n            return .active\n        }"),
            "Capture status should light up when monitoring is live, even if persisted intent is stale"
        )
        XCTAssertFalse(
            source.contains("if screenAnalysisEnabled && isCaptureMonitoring {\n            return .active\n        }"),
            "Capture status must not require persisted intent to match the live monitor"
        )
    }

    func testDashboardCaptureToggleDerivesFromLiveState() throws {
        let source = try dashboardSource()

        XCTAssertTrue(
            source.contains("syncCaptureState()\n        let enabled = !isCaptureLive"),
            "Capture toggles should reconcile the live monitor before deciding whether the click starts or stops capture"
        )
        XCTAssertFalse(
            source.contains("let enabled = !screenAnalysisEnabled"),
            "Capture toggles should not derive from stale persisted intent"
        )
    }

    func testListeningPillShowsAndTogglesCaptureMode() throws {
        let source = try dashboardSource()

        XCTAssertTrue(source.contains("@AppStorage(\"systemAudioCaptureMode\")"))
        XCTAssertTrue(source.contains("private var listeningModeTitle: String"))
        XCTAssertTrue(source.contains("return appState.isAwaitingMeeting ? \"Meetings only\" : \"In meeting\""))
        XCTAssertTrue(source.contains("HomeListeningStatusButton("))
        XCTAssertTrue(source.contains("modeAction: toggleListeningMode"))
        XCTAssertTrue(source.contains("AssistantSettings.shared.systemAudioCaptureMode = nextMode"))
        XCTAssertFalse(source.contains("OmiColors.purplePrimary"))
    }

    private func dashboardSource() throws -> String {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let dashboardURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift")
        return try String(contentsOf: dashboardURL, encoding: .utf8)
    }
}
