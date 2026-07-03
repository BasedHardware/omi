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

    func testHomeConnectorButtonsOpenSheetsDirectly() throws {
        let source = try dashboardSource()
        let importMethod = try methodBody(named: "openImportConnector", in: source)
        let exportMethod = try methodBody(named: "openExportDestination", in: source)

        XCTAssertTrue(source.contains("@State private var selectedImportConnector: ImportConnector?"))
        XCTAssertTrue(source.contains("@State private var selectedExportDestination: MemoryExportDestination?"))
        XCTAssertTrue(source.contains(".dismissableSheet(item: $selectedImportConnector)"))
        XCTAssertTrue(source.contains(".dismissableSheet(item: $selectedExportDestination)"))
        XCTAssertTrue(importMethod.contains("selectedImportConnector = ImportConnector.all.first { $0.id == connectorID }"))
        XCTAssertTrue(exportMethod.contains("selectedExportDestination = destination"))
        XCTAssertFalse(importMethod.contains("navigate(to: .apps)"))
        XCTAssertFalse(exportMethod.contains("navigate(to: .apps)"))
        XCTAssertFalse(importMethod.contains("desktopAutomationOpenImportRequested"))
        XCTAssertFalse(exportMethod.contains("desktopAutomationOpenExportRequested"))
    }

    private func dashboardSource() throws -> String {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let dashboardURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift")
        return try String(contentsOf: dashboardURL, encoding: .utf8)
    }

    private func methodBody(named name: String, in source: String) throws -> String {
        let pattern = #"private func \#(name)\([^\)]*\) \{([\s\S]*?)\n    \}"#
        let regex = try NSRegularExpression(pattern: pattern)
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        let match = try XCTUnwrap(regex.firstMatch(in: source, range: range))
        let bodyRange = try XCTUnwrap(Range(match.range(at: 1), in: source))
        return String(source[bodyRange])
    }
}
