import ContextCore
import XCTest

@testable import ContextApp

/// **The app-side half of "two builds may not share one platform identity".**
///
/// `Tests/ContextCoreTests/BuildIdentityTests` proves which identifier this process adopts and how
/// the Claude registration splits. This file covers the three values in the app target that macOS
/// itself keys on, each of which was a production literal and each of which a development build
/// therefore collided with: the `tccutil` line the user is told to run, the Keychain service, and
/// the log subsystem.
final class BuildIdentityTests: XCTestCase {

    private let shipping = ContextPaths.shippingBundleIdentifier
    private let development = ContextPaths.shippingBundleIdentifier + ".dev"

    /// **A dev build must not tell the user to reset the installed app's permission.**
    ///
    /// `tccutil reset ScreenCapture <id>` deletes the record for exactly one identifier. Handing a
    /// developer the production id repairs nothing on their build and destroys a grant on an app
    /// that was working — and it is the *only* remedy this state offers, so there is no second
    /// sentence to fall back on.
    func testADevelopmentBuildsResetCommandNamesItsOwnBundleAndNotTheShippingOne() {
        let command = Permissions.screenRecordResetCommand(for: development)

        XCTAssertEqual(command, "tccutil reset ScreenCapture \(development)")
        XCTAssertFalse(
            command.contains(shipping + " "), "a trailing production id is the grant this must not delete")
        XCTAssertTrue(command.hasSuffix(development))
    }

    /// A Keychain item's ACL is bound to the signature that created it, so a dev build and the
    /// release reading one service name is the login-keychain password sheet — unanswerable, and
    /// the same failure the move off the desktop app's item already fixed once.
    func testTheKeychainServiceIsPerBuild() {
        XCTAssertEqual(SessionStore.service(for: development), "\(development).session")
        XCTAssertNotEqual(SessionStore.service(for: development), SessionStore.service(for: shipping))
    }

    /// The other direction, and the one that stops this fix from silently renaming production: a
    /// release build's values are byte for byte what shipped. A changed Keychain service signs every
    /// existing install out; a changed `tccutil` line tells them to reset a record they do not have.
    func testAProductionBuildsValuesAreExactlyTheStringsThatShip() {
        XCTAssertEqual(
            Permissions.screenRecordResetCommand(for: shipping),
            "tccutil reset ScreenCapture com.omi.context-for-claude")
        XCTAssertEqual(SessionStore.service(for: shipping), "com.omi.context-for-claude.session")
    }

    /// The wiring: each shipped constant is the rule applied to the identifier this process resolved,
    /// not a literal sitting beside it.
    ///
    /// `os.Logger` never hands its subsystem back, so reading `ContextLog.subsystem` is the whole of
    /// what is observable there — this pins the constant, and the divergence itself is proved above.
    func testTheShippedConstantsFollowTheRunningBundle() {
        XCTAssertEqual(
            Permissions.screenRecordResetCommand,
            Permissions.screenRecordResetCommand(for: ContextPaths.bundleIdentifier))
        XCTAssertEqual(SessionStore.service, SessionStore.service(for: ContextPaths.bundleIdentifier))
        XCTAssertEqual(ContextLog.subsystem, ContextPaths.bundleIdentifier)
    }
}
