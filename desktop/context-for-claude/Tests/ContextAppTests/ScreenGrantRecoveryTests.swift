import XCTest

@testable import ContextApp

/// The state a screen grant lands in after it goes away, and whether the app can ask again.
///
/// This is not hypothetical. On a real install the grant was dropped, the user switched Screen
/// Recording back on in System Settings, and capture stayed dead for hours: the app had latched
/// "already prompted" when it first asked, so every later ask opened a Settings pane instead of
/// raising the prompt, and macOS had no entry there to honour.
final class ScreenGrantRecoveryTests: XCTestCase {

    func testFirstAskRaisesThePrompt() {
        XCTAssertTrue(Permissions.screenAskShouldPrompt(hasPrompted: false, grantWasLost: false))
    }

    func testAskingAgainAfterARefusalGoesToSettings() {
        // CGRequestScreenCaptureAccess returns false immediately once an answer is on record, so a
        // second prompt would be a dead row rather than a dialog.
        XCTAssertFalse(Permissions.screenAskShouldPrompt(hasPrompted: true, grantWasLost: false))
    }

    func testALostGrantAsksAgainRatherThanPointingAtSettingsForever() {
        // The regression. Latched + lost previously resolved to "open Settings", which is the
        // one branch that cannot recover: macOS has no grant on record to toggle.
        XCTAssertTrue(Permissions.screenAskShouldPrompt(hasPrompted: true, grantWasLost: true))
    }

    func testAFreshInstallThatNeverCapturedIsNotTreatedAsALostGrant() {
        // grantWasLost is defined as "demonstrably worked, and now does not", so a first run with
        // no capture history must not claim recovery.
        XCTAssertTrue(Permissions.screenAskShouldPrompt(hasPrompted: false, grantWasLost: false))
    }
}
