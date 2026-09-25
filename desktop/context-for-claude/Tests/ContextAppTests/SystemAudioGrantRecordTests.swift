import XCTest

@testable import ContextApp

/// **The system-audio half of the permission this app asked for over and over, and the half it
/// stopped asking for at all.**
///
/// Two defects, one cause, and it is the cause `ScreenStaleGrantTests` and the keychain fix already
/// document from their own side: a durable record that claims to know what TCC will do, consulted by
/// something that runs on a clock. TCC keys every grant to a code signature and drops the record
/// without a word when that signature changes — a re-sign, or an update shipped under a different
/// identity, which is exactly what 1.0.4 was. `UserDefaults` does not change, so both records survive
/// the thing they describe.
///
/// - `context.permission.systemAudio.prompted` claims the consent dialog has been spent. Left true
///   over a dropped record it licensed the background poll to build a global CoreAudio process tap,
///   and macOS answers a tap with no record by putting the consent dialog on screen. `Permissions
///   .check(.systemAudio)` is a *read*, the onboarding card polls it every 0.4 s and the menu bar
///   polls it too, so the dialog came back every 30 s for as long as the app was running.
/// - `context.permission.systemAudio.granted` claims the grant itself, and is the one capability
///   answer in the app that nothing could falsify: every refresh path returns at its first guard
///   once it reads `true`. Measured on the reporting machine on 15 August 2026, minutes after the
///   notarized 1.0.4 replaced an ad-hoc-signed build:
///
///   ```
///   $ defaults read com.omi.context-for-claude
///       "context.permission.systemAudio.granted" = 1;
///       "context.permission.systemAudio.prompted" = 1;
///   ```
///
///   With the TCC record gone, that `1` is the menu bar reading "Granted" over a dead tap, the
///   onboarding card counting the row answered and never offering it, and the capture path finding
///   out alone, as an opaque device error with no route to the switch.
final class SystemAudioGrantRecordTests: XCTestCase {

    // MARK: - A read may not raise a dialog

    /// **The defect, stated as the rule that now governs the read.**
    ///
    /// Nothing the user did starts a background probe, so nothing the user did may raise a consent
    /// dialog. The only evidence that a tap cannot raise one is that this process has already had a
    /// tap answered — a fact about the run, which is precisely what the persisted flag was not.
    func testAReadCannotSpendATapBeforeThisProcessHasHadOneAnswered() {
        for cached in [nil, false] as [Bool?] {
            XCTAssertFalse(
                Permissions.unattendedProbeIsDue(
                    cached: cached, tapAnsweredInThisProcess: false, secondsSinceProbe: 3_600),
                "a poll built a CoreAudio tap on a launch where nothing had been clicked — which is "
                    + "the consent dialog arriving every 30 seconds over a user who asked for nothing")
        }
    }

    /// A grant is still trusted for the life of the process, whatever else is true: a second global
    /// tap while capture is live is the one thing that can knock the live tap over.
    func testAGrantIsNeverReProbed() {
        XCTAssertFalse(
            Permissions.unattendedProbeIsDue(
                cached: true, tapAnsweredInThisProcess: true, secondsSinceProbe: 3_600))
    }

    /// And the schedule this replaces is kept, not weakened. Once the user has clicked the row, the
    /// prompt genuinely is spent for this process, and the slow re-probe is what notices a switch
    /// flipped in System Settings — the *"even after I turned it on this still doesnt go away"* fix.
    func testOnceATapHasBeenAnsweredTheSlowScheduleResumes() {
        XCTAssertFalse(
            Permissions.unattendedProbeIsDue(
                cached: false, tapAnsweredInThisProcess: true, secondsSinceProbe: 1.5),
            "a probe on every poll is a tap rebuilt four times a second")
        XCTAssertTrue(
            Permissions.unattendedProbeIsDue(
                cached: false, tapAnsweredInThisProcess: true,
                secondsSinceProbe: Permissions.systemAudioProbeInterval + 1))
        XCTAssertTrue(
            Permissions.unattendedProbeIsDue(
                cached: nil, tapAnsweredInThisProcess: true,
                secondsSinceProbe: Permissions.systemAudioProbeInterval + 1),
            "an unknown answer is the one state that could never recover on its own")
    }

    // MARK: - A record may not outlive the signature that earned it

    /// The rule, in the two directions that keep less rather than more.
    func testRecordsWithNoStampDoNotSurviveAndAnUnknownSignatureChangesNothing() {
        XCTAssertFalse(
            Permissions.systemAudioRecordsSurvive(stored: nil, current: "sig-a"),
            "records written before anything stamped a signature were written under an unknown one")
        XCTAssertFalse(Permissions.systemAudioRecordsSurvive(stored: "sig-a", current: "sig-b"))
        XCTAssertTrue(Permissions.systemAudioRecordsSurvive(stored: "sig-a", current: "sig-a"))
        XCTAssertTrue(
            Permissions.systemAudioRecordsSurvive(stored: "sig-a", current: nil),
            "an unanswerable question is not a reason to spend a working answer")
    }

    /// **The update, run through the real mutation.**
    ///
    /// The state is the one measured on the reporting machine: a grant and a spent prompt, written by
    /// a build that stamped no signature. Both have to go, and the row has to end up reading
    /// not-granted — which is what puts it back in front of the user and back in reach of the
    /// capture path's "macOS dropped this app's permission" copy.
    func testTheGrantAnAdHocBuildLeftBehindIsSpentWhenTheSignatureChanges() throws {
        let defaults = try suite(#function)

        defaults.set(true, forKey: Self.granted)
        defaults.set(1_785_696_758.0, forKey: Self.probedAt)
        defaults.set(true, forKey: Self.prompted)

        XCTAssertTrue(
            Permissions.reconcileSystemAudioRecords(defaults: defaults, signature: "notarized-1.0.4"))

        XCTAssertNil(
            defaults.object(forKey: Self.granted),
            "the menu bar went on reading \"Granted\" over a TCC record macOS had dropped")
        XCTAssertNil(defaults.object(forKey: Self.probedAt))
        XCTAssertNil(
            defaults.object(forKey: Self.prompted),
            "a spent-prompt claim about a dropped record sends the row's first click to a pane "
                + "instead of to the dialog that is about to appear")
        XCTAssertEqual(defaults.string(forKey: Self.signature), "notarized-1.0.4")
    }

    /// And it happens once. A reconciliation that spent the records on every read would be a grant
    /// the user could never keep.
    func testTheSameSignatureSpendsNothingTwice() throws {
        let defaults = try suite(#function)
        Permissions.reconcileSystemAudioRecords(defaults: defaults, signature: "sig-a")

        defaults.set(true, forKey: Self.granted)
        defaults.set(true, forKey: Self.prompted)

        XCTAssertFalse(Permissions.reconcileSystemAudioRecords(defaults: defaults, signature: "sig-a"))
        XCTAssertEqual(defaults.object(forKey: Self.granted) as? Bool, true)
        XCTAssertEqual(defaults.object(forKey: Self.prompted) as? Bool, true)
    }

    /// A signature that cannot be read leaves everything alone, including the stamp.
    func testAnUnknownSignatureLeavesTheRecordsAndTheStampAlone() throws {
        let defaults = try suite(#function)
        defaults.set(true, forKey: Self.granted)
        defaults.set("sig-a", forKey: Self.signature)

        XCTAssertFalse(Permissions.reconcileSystemAudioRecords(defaults: defaults, signature: nil))
        XCTAssertEqual(defaults.object(forKey: Self.granted) as? Bool, true)
        XCTAssertEqual(defaults.string(forKey: Self.signature), "sig-a")
    }

    /// **The two halves together, which is the only way either is safe.**
    ///
    /// Dropping the stale grant is what puts the row back in front of the user; on its own it would
    /// also hand the background poll a `nil` cache beside a durable "the prompt is spent", which is
    /// the dialog loop. The reconciliation spends the prompt record and the probe is latched to this
    /// process, so the update lands on a row that asks and a poll that does not.
    func testTheUpdateProducesAnAskableRowAndNoUnattendedProbe() throws {
        let defaults = try suite(#function)
        defaults.set(true, forKey: Self.granted)
        defaults.set(true, forKey: Self.prompted)
        Permissions.reconcileSystemAudioRecords(defaults: defaults, signature: "notarized-1.0.4")

        let cached = defaults.object(forKey: Self.granted) as? Bool
        XCTAssertNil(cached, "the row has to be offered again, so the cached answer cannot stand")
        XCTAssertFalse(
            Permissions.unattendedProbeIsDue(
                cached: cached, tapAnsweredInThisProcess: false, secondsSinceProbe: 3_600),
            "every updating install would meet the consent dialog on a 30 second loop")
    }

    // MARK: - Plumbing

    private static let granted = "context.permission.systemAudio.granted"
    private static let probedAt = "context.permission.systemAudio.probedAt"
    private static let prompted = "context.permission.systemAudio.prompted"
    private static let signature = "context.permission.systemAudio.signature"

    /// A domain of its own per test. The keys under test are the app's real ones, so a suite is what
    /// keeps a test run from reading — or writing — the records of the install it is running on.
    private func suite(_ name: String) throws -> UserDefaults {
        let id = "context.tests.systemAudio.\(name).\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: id))
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: id) }
        return defaults
    }
}
