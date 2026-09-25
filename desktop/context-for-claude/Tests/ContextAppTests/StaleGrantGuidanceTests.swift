import CoreAudio
import XCTest

@testable import ContextApp

/// **The app telling the user to switch on a switch they can see is already on.**
///
/// Observed on this machine on 15 August 2026, on the shipped notarized 1.0.4. The app reported
/// `screen: not granted — Action required` and the popover said *"Screen Recording has stopped
/// working — macOS dropped this app's grant … Switch it back on in System Settings ▸ Privacy &
/// Security ▸ Screen & System Audio Recording."* That pane was opened at once: the **Context for
/// Claude** toggle was already **on**. The system log says why:
///
/// ```
/// tccd: Failed to match existing code requirement for subject com.omi.context-for-claude and
///       service kTCCServiceMicrophone
/// ```
///
/// A TCC record carries the code requirement of the binary that earned it, so after a re-sign the
/// daemon refuses the app while System Settings keeps rendering the row from the record it still
/// holds. Both halves of the report are true at once — genuinely denied, genuinely switched on — and
/// the instruction was the one thing that could not work. A user who follows it, sees it already
/// enabled and concludes the app is broken is behaving correctly.
///
/// The remedy that does work is the one nothing said: turn it **off** and back on, which is what
/// makes macOS write the record against the new signature. These tests hold the guidance to that.
/// They assert the distinguishing content — off *and* back on, and reopen — not whole sentences: a
/// test that pins the wording becomes a chore the next edit has to service, and pinning it would not
/// have caught the shipped defect anyway, which was a perfectly well-formed wrong instruction.
final class StaleGrantGuidanceTests: XCTestCase {

    /// Every capability whose grant dies to the same `tccd` mismatch. Microphone and system audio are
    /// in this list because the log line above is `kTCCServiceMicrophone` — the screen was merely the
    /// half that was noticed first.
    private static let capabilities: [Capability] = [.microphone, .systemAudio, .screen]

    func testTheRemedyIsToTurnItOffAndBackOnRatherThanOn() {
        for capability in Self.capabilities {
            let reason = Permissions.staleGrantReason(subject: "Call audio", for: capability)
                .lowercased()

            XCTAssertTrue(
                reason.contains("off and back on"),
                "\(capability) still tells the user to do something other than re-create the TCC "
                    + "record; switching a switch that is already on is the shipped defect")
            XCTAssertTrue(
                reason.contains("reopen"),
                "\(capability) leaves out the second half — macOS itself offers to quit and reopen "
                    + "when a running app's row is changed, and screen capture rights are only "
                    + "re-read when the process reconnects")
        }
    }

    /// The exact sentence that shipped, as a thing the copy may no longer say. `switch it back on`
    /// presumes an off switch, which is the state the user is *not* in.
    func testTheGuidanceNoLongerPresumesTheSwitchIsOff() {
        for capability in Self.capabilities {
            let reason = Permissions.staleGrantReason(subject: "Screen Recording", for: capability)
                .lowercased()
            XCTAssertFalse(reason.contains("switch it back on"))
            XCTAssertTrue(
                reason.contains("may still look on"),
                "the user is looking at an enabled switch; guidance that does not account for that "
                    + "reads as the app being broken")
        }
    }

    /// Naming the pane is not decoration: that pane carries two lists and this app appears in both,
    /// so a user sent to the top of it toggles the screen row and the call half stays dead.
    func testSystemAudioNamesTheListItsRowIsActuallyIn() {
        XCTAssertTrue(
            Permissions.staleGrantReason(subject: "Call audio", for: .systemAudio)
                .contains("System Audio Recording Only"))
    }

    // MARK: - The surfaces that carry it

    func testTheScreenBlockCarriesTheRemedyRatherThanItsOwnSpelling() {
        XCTAssertEqual(
            Permissions.ScreenBlock.grantLost.reason,
            Permissions.staleGrantReason(subject: "Screen Recording", for: .screen),
            "the popover, the log and the MCP `status` tool all read this one string; a second "
                + "spelling of the remedy is a second chance to get it wrong")
        XCTAssertTrue(
            Permissions.ScreenBlock.grantLost.isRegression,
            "a promise that stopped being kept is still logged as one")
    }

    /// The engine's audio half, which is where microphone and system audio meet this state.
    func testAnAudioComponentThatLostItsGrantReportsTheRemedy() {
        for capability in [Capability.microphone, .systemAudio] {
            let state = Engine.missingPermissionState(
                label: "Call audio", capability: capability, hasEverCaptured: true)

            guard case .blocked(let reason) = state else {
                return XCTFail("a grant this install used and lost needs the user, so it is blocked")
            }
            XCTAssertEqual(reason, Permissions.staleGrantReason(subject: "Call audio", for: capability))
        }
    }

    /// The half worth guarding hardest, unchanged by this fix: a capability nobody ever granted is
    /// the user's own choice. Telling them to toggle a switch they never touched would be the same
    /// class of untrue sentence, aimed at everyone who simply declined.
    func testAPermissionThatWasNeverGrantedIsNotToldToToggleAnything() {
        let state = Engine.missingPermissionState(
            label: "Call audio", capability: .systemAudio, hasEverCaptured: false)

        guard case .off(let reason) = state else {
            return XCTFail("nothing has gone wrong, so nothing may read as broken")
        }
        XCTAssertFalse(reason.lowercased().contains("off and back on"))
    }
}

/// **A system-audio tap that fails at capture time, over a cached grant that says it cannot have.**
///
/// System audio is the one capability with no preflight, so `Permissions.check` answers it from
/// `UserDefaults`. `reconcileSystemAudioRecords` falsifies that cache at launch, per code signature —
/// and nothing falsified it *within* a run. So a grant revoked while the app was capturing left the
/// menu bar reading "Granted" and the onboarding card counting the row answered, over a tap CoreAudio
/// was refusing, until the next launch. The screen half has had `noteScreenCaptureDeclined` for this
/// since the WindowServer loop was fixed; this is the missing other side of it.
///
/// The driver below is `ScreenStaleGrantTests.Launch` one stream over: the production decision
/// functions, played tick by tick, with the OS injected. Nothing here touches CoreAudio, TCC, or the
/// real records.
final class SystemAudioTapRefusalTests: XCTestCase {

    // MARK: - The driver

    /// One run of the real gate. `tapAttempts` counts taps that reach the HAL, which is what a user
    /// pays for: every attempt is a global process tap built and torn down, and each one macOS has no
    /// record for is a consent dialog on screen.
    private struct Session {
        /// What `context.permission.systemAudio.granted` says. `true` throughout: a cached grant over
        /// a dead tap is the whole defect.
        var storedGrant: Bool? = true
        /// Whether this install has ever captured, which separates a lost grant from an unasked one.
        var hasEverCaptured = true

        /// The injected OS: what `AudioHardwareCreateProcessTap` answers.
        var tapStatus: OSStatus = noErr

        private(set) var tapAttempts = 0
        /// What `Permissions.noteSystemAudioTapRefused()` records, process-scoped.
        private(set) var tapRefused = false
        private(set) var state: ComponentState?

        /// `Engine.startAudio`'s permission gate, then the device start it guards.
        mutating func tick() {
            let granted = Permissions.systemAudioIsGranted(
                cached: storedGrant, tapRefused: tapRefused) ?? false
            guard granted else {
                state = Engine.missingPermissionState(
                    label: "Call audio", capability: .systemAudio, hasEverCaptured: hasEverCaptured)
                return
            }

            tapAttempts += 1
            if SystemAudioCapture.tapCreationWasRefused(tapStatus) {
                tapRefused = true
                state = Engine.missingPermissionState(
                    label: "Call audio", capability: .systemAudio, hasEverCaptured: hasEverCaptured)
                return
            }
            state = tapStatus == noErr ? .live : .blocked("Call audio stopped — the tap failed")
        }

        /// The user re-gave the consent and a probe got its tap — `Permissions.recordSystemAudio`
        /// writing a grant, which is the one thing that clears the refusal.
        mutating func consentRecordedAgain() {
            tapStatus = noErr
            storedGrant = true
            tapRefused = false
        }

        mutating func run(ticks: Int) {
            for _ in 0..<ticks { tick() }
        }
    }

    // MARK: - The regression

    func testARefusedTapLowersTheGrantInsteadOfBeingRetriedForever() {
        var session = Session()
        // Whatever the denial's status is, it is not one of the two that mean "the HAL cannot answer
        // anything right now".
        session.tapStatus = kAudioHardwareIllegalOperationError

        // Half an hour of the maintenance loop's thirty-second retry.
        session.run(ticks: 60)

        XCTAssertEqual(
            session.tapAttempts, 1,
            "a refusal has to reach `Permissions`, or the cache goes on saying granted and the "
                + "engine goes on building a tap macOS will not give it")
    }

    func testTheRefusalIsReportedAsTheStaleGrantItIs() {
        var session = Session()
        session.tapStatus = kAudioHardwareIllegalOperationError
        session.run(ticks: 2)

        XCTAssertEqual(
            session.state,
            .blocked(Permissions.staleGrantReason(subject: "Call audio", for: .systemAudio)),
            "system audio has to reach the user the way the screen and the microphone already do — "
                + "blocked, with the remedy that works, rather than an opaque HAL status")
    }

    /// The half that makes the count above meaningful. Over-classifying would send a user to System
    /// Settings over a hiccup, which is the same lie pointing the other way.
    func testAWorkingTapIsNeverStoodDown() {
        var session = Session()
        session.run(ticks: 60)

        XCTAssertEqual(session.tapAttempts, 60, "nothing refused this process, so nothing may stop it")
        XCTAssertEqual(session.state, .live)
    }

    /// A `coreaudiod` that is restarting — this file's own documented case, since HAL calls can block
    /// for seconds after a wake from sleep, which is exactly when capture restarts. The right answer
    /// is the next attempt, not a sentence about System Settings.
    func testAHalThatCannotAnswerYetIsRetriedRatherThanBlamedOnThePermission() {
        for status in [kAudioHardwareNotRunningError, kAudioHardwareNotReadyError] {
            var session = Session()
            session.tapStatus = status
            session.run(ticks: 5)

            XCTAssertEqual(session.tapAttempts, 5, "a transient HAL failure is worth another attempt")
            XCTAssertFalse(
                session.tapRefused,
                "\(status) says the HAL cannot answer anything, which is not macOS refusing us")
        }
    }

    // MARK: - The rules, separately

    func testOnlyTapCreationIsJudgedAndOnlyWhenItFailed() {
        XCTAssertFalse(
            SystemAudioCapture.tapCreationWasRefused(noErr),
            "a tap that was created is a tap macOS allowed")
        XCTAssertTrue(SystemAudioCapture.tapCreationWasRefused(kAudioHardwareIllegalOperationError))
        XCTAssertTrue(SystemAudioCapture.tapCreationWasRefused(kAudioDevicePermissionsError))
    }

    func testARefusalOutranksTheCachedAnswerAndNothingElseChanges() {
        XCTAssertEqual(
            Permissions.systemAudioIsGranted(cached: true, tapRefused: true), false,
            "the cache was the one capability answer nothing could falsify inside a run")
        XCTAssertEqual(Permissions.systemAudioIsGranted(cached: true, tapRefused: false), true)
        XCTAssertEqual(
            Permissions.systemAudioIsGranted(cached: nil, tapRefused: false), nil,
            "never probed is still never probed — the row says \"Open\", not \"Action required\"")
        XCTAssertEqual(Permissions.systemAudioIsGranted(cached: false, tapRefused: false), false)
    }

    /// And the refusal has to be leaveable within the run. The row's own click is what probes, a probe
    /// that gets its tap is the only evidence the consent is back, and `recordSystemAudio` clears the
    /// refusal on exactly that. Without the clearing this fix would trade a cache that could not go
    /// down for one that could not come back up — a permission the user is told to re-give and then
    /// not believed about.
    func testConsentGivenAgainEndsTheRefusalWithoutARelaunch() {
        var session = Session()
        session.tapStatus = kAudioHardwareIllegalOperationError
        session.run(ticks: 3)
        XCTAssertNotEqual(session.state, .live, "refused, and reported")

        session.consentRecordedAgain()
        session.run(ticks: 1)

        XCTAssertEqual(session.state, .live)
        XCTAssertEqual(session.tapAttempts, 2, "one refused attempt, then one that was allowed")
    }
}
