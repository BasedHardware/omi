import Foundation
import Security
import XCTest

@testable import ContextApp

/// **The password sheet this app put up over and over for an item it can never read.**
///
/// Reported verbatim: *"make sure you dont keep asking keychain access every few seconds its so
/// pissing off and unnecessary."* What was on screen was macOS's own sheet — *"Context for Claude
/// wants to access key 'Omi Context for Claude' in your keychain. To allow this, enter the 'login'
/// keychain password."* — with no password that answers it.
///
/// The cause is the one the Screen Recording fix on this same branch already met once
/// (`ScreenStaleGrantTests`): the bundle was re-signed from an ad-hoc build to a notarized Developer
/// ID one. A login-keychain item's access-control list names the *code signature* that created it,
/// so the new binary is not on the trusted-application list of the item the old binary wrote.
/// `securityd` answers every such read with the sheet, and no answer the user can give changes a
/// signature — a second read is the same sheet with the same outcome.
///
/// `SessionStore.load()` classified that refusal as `default:` — one log line and `nil` — which is
/// indistinguishable from "nothing stored". `nil` is not a status: it left the door open for the
/// next reader, and each reader is another sheet.
///
/// The seam is the OS. Nothing here touches a keychain, a `SecItem` call or a signature: these drive
/// `SessionStore`'s real read and write decisions with the OSStatus injected, and count how many
/// times the production path is allowed to ask.
final class KeychainRefusalTests: XCTestCase {

    // MARK: - The injected OS

    /// A keychain that answers whatever it is told to, and counts how often it was asked.
    ///
    /// The count is the whole assertion: on a real Mac, one read of a refusing item is one password
    /// sheet, so "reads" and "sheets the user has to look at" are the same number.
    private final class FakeKeychain {
        private(set) var reads = 0
        private(set) var updates = 0
        private(set) var adds = 0
        private(set) var deletes = 0

        var readAnswer: SessionStore.KeychainRead = .failed(errSecItemNotFound)
        var updateAnswer: OSStatus = errSecSuccess
        var addAnswer: OSStatus = errSecSuccess
        var deleteAnswer: OSStatus = errSecSuccess

        func read() -> SessionStore.KeychainRead {
            reads += 1
            return readAnswer
        }

        var ops: SessionStore.KeychainOps {
            SessionStore.KeychainOps(
                update: { _ in
                    self.updates += 1
                    return self.updateAnswer
                },
                add: { _ in
                    self.adds += 1
                    return self.addAnswer
                },
                delete: {
                    self.deletes += 1
                    return self.deleteAnswer
                })
        }
    }

    /// A session shaped like a real stored one. The values are never sent anywhere — the only thing
    /// this suite cares about is that a healthy read round-trips.
    private static let storedSession = OmiSession(
        idToken: "id-token", refreshToken: "refresh-token",
        expiryTime: 4_102_444_800, tokenUserId: "uid-1")

    /// One launch's worth of asking. The app reads once today, but the count is what the fix is
    /// about, so the driver asks far more times than any launch could.
    private static let attempts = 200

    // MARK: - The bug

    /// **Exactly one read per process, for every refusal that means "not this signature".**
    ///
    /// Before the fix each of these left `SessionStore` willing to ask again, which on the affected
    /// Mac is one login-keychain sheet per ask.
    func testDefinitiveRefusalIsAskedExactlyOnce() {
        for status in [errSecAuthFailed, errSecUserCanceled, errSecInteractionNotAllowed, errSecInteractionRequired] {
            let keychain = FakeKeychain()
            keychain.readAnswer = .failed(status)
            let refusal = KeychainRefusal()

            for _ in 0..<Self.attempts {
                XCTAssertNil(
                    SessionStore.load(read: keychain.read, refusal: refusal),
                    "a refused read must report no session (OSStatus \(status))")
            }

            XCTAssertEqual(
                keychain.reads, 1,
                "OSStatus \(status) cannot be retried into a success, so it must reach the keychain once")
            XCTAssertTrue(refusal.isSignalled, "OSStatus \(status) must be recorded as a refusal")
        }
    }

    // MARK: - The states that must not be latched

    /// **"No credential stored" is not a refusal.** It raises no sheet, it is the ordinary first-run
    /// and signed-out state, and latching it would make a real sign-in unreadable for the rest of the
    /// launch. So it keeps asking, and it keeps reporting the plain signed-out answer.
    func testMissingItemKeepsTheOrdinarySignedOutPath() {
        let keychain = FakeKeychain()
        keychain.readAnswer = .failed(errSecItemNotFound)
        let refusal = KeychainRefusal()

        for _ in 0..<Self.attempts {
            XCTAssertNil(SessionStore.load(read: keychain.read, refusal: refusal))
        }

        XCTAssertEqual(keychain.reads, Self.attempts, "errSecItemNotFound prompts for nothing and must not be latched")
        XCTAssertFalse(refusal.isSignalled)
    }

    /// A keychain that is locked or faulting heals, and it does not put the trusted-application
    /// sheet up. Those keep the non-latching path they already had.
    func testRecoverableFailuresAreNotLatched() {
        for status in [errSecNotAvailable, errSecIO, errSecDecode] {
            let keychain = FakeKeychain()
            keychain.readAnswer = .failed(status)
            let refusal = KeychainRefusal()

            for _ in 0..<Self.attempts {
                XCTAssertNil(SessionStore.load(read: keychain.read, refusal: refusal))
            }

            XCTAssertEqual(keychain.reads, Self.attempts, "OSStatus \(status) is recoverable and must stay retryable")
            XCTAssertFalse(refusal.isSignalled)
        }
    }

    /// **A healthy read is never suppressed.** The rule only ever stands between the app and an
    /// answer macOS has already given, so a Mac whose item this binary owns is untouched by it.
    func testHealthyReadIsNeverSuppressed() throws {
        let keychain = FakeKeychain()
        keychain.readAnswer = .succeeded(try JSONEncoder().encode(Self.storedSession))
        let refusal = KeychainRefusal()

        for _ in 0..<Self.attempts {
            XCTAssertEqual(SessionStore.load(read: keychain.read, refusal: refusal), Self.storedSession)
        }

        XCTAssertEqual(keychain.reads, Self.attempts)
        XCTAssertFalse(refusal.isSignalled)
    }

    // MARK: - Classification

    /// The OSStatus values by number, not by name, because the rule has to hold against the values
    /// `Security.framework`'s `SecBase.h` actually ships:
    /// `errSecAuthFailed = -25293`, `errSecUserCanceled = -128`,
    /// `errSecInteractionNotAllowed = -25308`, `errSecInteractionRequired = -25315`,
    /// `errSecItemNotFound = -25300`.
    func testRefusalClassificationMatchesTheDocumentedValues() {
        for status: OSStatus in [-25293, -128, -25308, -25315] {
            XCTAssertTrue(SessionStore.isDefinitiveRefusal(status), "\(status) is a refusal no retry can satisfy")
        }
        for status: OSStatus in [-25300, errSecSuccess, errSecNotAvailable, errSecIO] {
            XCTAssertFalse(SessionStore.isDefinitiveRefusal(status), "\(status) must keep its recoverable path")
        }
    }

    // MARK: - The stale item

    /// **Signing in replaces the item the old signature left behind, once.**
    ///
    /// Without this, the item refuses every update forever: sign-in reports *"couldn't store the
    /// session in your Keychain. Try again."*, the user tries again, and each attempt is another
    /// sheet. The delete is safe only on this path — a live session is already in hand, so the
    /// credential being dropped is one nothing in this process could ever have read.
    func testSignInReplacesAnItemThisSignatureCannotUpdate() {
        let keychain = FakeKeychain()
        keychain.updateAnswer = errSecAuthFailed
        let refusal = KeychainRefusal()
        refusal.signal()

        XCTAssertTrue(SessionStore.save(Self.storedSession, ops: keychain.ops, refusal: refusal))

        XCTAssertEqual(keychain.updates, 1, "one refused update, not a retry loop")
        XCTAssertEqual(keychain.deletes, 1, "the unreadable item is removed exactly once")
        XCTAssertEqual(keychain.adds, 1, "and replaced with the session that just signed in")
        XCTAssertFalse(refusal.isSignalled, "the item is this signature's again, so the recorded refusal is spent")
    }

    /// A **failed read** must never delete anything. The item may be perfectly good and readable by
    /// a correctly-signed build; destroying it on the way past would take a working credential with
    /// it.
    func testARefusedReadDeletesNothing() {
        let keychain = FakeKeychain()
        keychain.readAnswer = .failed(errSecAuthFailed)
        let refusal = KeychainRefusal()

        for _ in 0..<Self.attempts {
            XCTAssertNil(SessionStore.load(read: keychain.read, refusal: refusal))
        }

        XCTAssertEqual(keychain.deletes, 0)
        XCTAssertEqual(keychain.adds, 0)
        XCTAssertEqual(keychain.updates, 0)
    }

    /// The ordinary first write on a Mac with no item yet: update misses, add lands, nothing is
    /// deleted.
    func testFirstSaveAddsWithoutDeleting() {
        let keychain = FakeKeychain()
        keychain.updateAnswer = errSecItemNotFound
        let refusal = KeychainRefusal()

        XCTAssertTrue(SessionStore.save(Self.storedSession, ops: keychain.ops, refusal: refusal))

        XCTAssertEqual(keychain.updates, 1)
        XCTAssertEqual(keychain.adds, 1)
        XCTAssertEqual(keychain.deletes, 0, "a missing item is not a stale item")
    }
}
