import XCTest

final class DashboardHomePolicyTests: XCTestCase {
    func testLegacyHomeIsDocumentedAsTemporaryFallback() throws {
        let policy = try policySource()
        let settings = try settingsSource()

        XCTAssertTrue(policy.contains("The redesigned Home is the canonical desktop dashboard"))
        XCTAssertTrue(policy.contains("two stable desktop releases"))
        XCTAssertTrue(policy.contains("New dashboard work does not need a parallel legacy version"))
        XCTAssertTrue(settings.contains("Use legacy Home design"))
        XCTAssertTrue(settings.contains("Temporary fallback during the redesigned Home rollout"))
        XCTAssertFalse(settings.contains("Use old Home design"))
    }

    private func policySource() throws -> String {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let policyURL = testsURL
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("docs/dashboard-home.md")
        return try String(contentsOf: policyURL, encoding: .utf8)
    }

    private func settingsSource() throws -> String {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let settingsURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent(
                "Sources/MainWindow/Pages/Settings/Sections/SettingsContentView+Assistants.swift"
            )
        return try String(contentsOf: settingsURL, encoding: .utf8)
    }
}
