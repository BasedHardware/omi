import XCTest
@testable import ContextApp

final class MenuBarPresentationTests: XCTestCase {
    func testConnectorSetupCopyCallsOutLocalConfigurationWithoutClaimingAClaudeAccount() {
        let copy = OnboardingConnectorCopy(surfaces: [])

        XCTAssertEqual(copy.title, "Bring Claude in")
        XCTAssertEqual(copy.action, "Set up Claude")
        XCTAssertTrue(copy.detail.contains("local connector"))
        XCTAssertFalse(copy.detail.localizedCaseInsensitiveContains("account"))
        XCTAssertFalse(copy.detail.localizedCaseInsensitiveContains("connected"))
    }

    func testConnectorSetupCopyNamesOnlyLocallyConfiguredSurfaces() {
        let copy = OnboardingConnectorCopy(surfaces: [.claudeCode])

        XCTAssertEqual(copy.title, "Claude Code is ready")
        XCTAssertEqual(copy.action, "Continue")
        XCTAssertEqual(copy.detail, "The local connector is configured for Claude Code.")
    }

}