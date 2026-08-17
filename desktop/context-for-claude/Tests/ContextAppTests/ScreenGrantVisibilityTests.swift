import XCTest

@testable import ContextApp

// MARK: - A grant this process cannot see

/// **The reported bug, as the measurement that produced it.**
///
/// Reported twice, in the user's words: *"overlay blocks permissions settings screen"* and
/// *"Permission is already on but it's still asking for it"* — with a screenshot of the onboarding
/// row reading "Asking…" beside a Screen & System Audio Recording list in which Context for Claude
/// is switched **on**.
///
/// The measurement, taken on this Mac on 16 August 2026 against the shipped notarized 1.0.11, is
/// the external source these expectations come from — not from reading the code back to itself:
///
/// ```text
/// before relaunch:  screen  granted false  detail "Open"     capturing false
/// after  relaunch:  screen  granted true   detail "Granted"  capturing true
/// ```
///
/// Nothing was toggled between those two reads, no `tccutil` was run, and the switch was on for
/// both. `CGPreflightScreenCaptureAccess()` is answered per *process*: the window server fixes what
/// a process may capture when that process connects, so a grant made afterwards reads `false` for
/// the rest of that process's life however many times it is asked.
///
/// That is why polling could never have fixed this and why the app must offer a reopen instead. It
/// is also why the reopen offer was unreachable: `screenNeedsRelaunch` gated itself behind the very
/// preflight that is false in exactly this state.
final class ScreenGrantVisibilityTests: XCTestCase {

    /// The regression itself. Once the user has been sent to the Screen Recording pane, a `false`
    /// preflight is not evidence that the switch is off — it is the one answer this process is
    /// incapable of updating. Offering the reopen is the only move left that can change anything.
    func testAFalsePreflightAfterSendingTheUserToThePaneStillOffersTheReopen() {
        XCTAssertTrue(
            Permissions.screenRelaunchOffer(preflight: false, settingsWasOpened: true),
            "this is the shipped bug: the row sat on \"Asking…\" over a switch that was already on, "
                + "because a stale preflight was read as a refusal")
    }

    /// The other half of the same rule, and what keeps the offer from becoming a loop. A process
    /// that has asked nothing of the user has no reason to tell them to reopen: reopening would
    /// change nothing, and the row should read as an offer to grant.
    ///
    /// `screenSettingsWasOpened` is process-scoped and never persisted, so this is also the state
    /// every successor starts in — which is what bounds the offer to once per process rather than
    /// once per poll.
    func testAProcessThatHasAskedNothingDoesNotTellAnybodyToReopen() {
        XCTAssertFalse(
            Permissions.screenRelaunchOffer(preflight: false, settingsWasOpened: false),
            "a reopen offered before the user has been sent anywhere is a loop, not a remedy")
    }

    /// A grant the preflight can actually see never depends on this rule at all — that path keeps
    /// the persisted flag and the staleness check. Pinned so the guard cannot be narrowed into
    /// covering only the case it was written for.
    func testATruePreflightIsAnsweredWithoutConsultingWhereTheUserHasBeen() {
        for opened in [true, false] {
            XCTAssertTrue(Permissions.screenRelaunchOffer(preflight: true, settingsWasOpened: opened))
        }
    }

    // MARK: - The sentences people actually read

    /// The screen row must not promise to notice a switch macOS will not let it see. The shared
    /// caption — "Switch it on and I'll notice" — is true for microphone and system audio and false
    /// for this one, and it is what left the reporter watching a row that never moved.
    func testTheScreenWaitDoesNotPromiseToNoticeTheSwitch() {
        let caption = PermissionGate.waitingCaption(for: .screen)
        XCTAssertFalse(
            caption.contains("I’ll notice"),
            "screen recording cannot be noticed in-process; promising it is the reported bug")
        XCTAssertTrue(
            caption.localizedCaseInsensitiveContains("reopen"),
            "the caption has to name the only thing that actually works")
    }

    /// The non-screen capabilities keep the promise, because for them it is true. This is the guard
    /// against "fixing" the screen sentence by flattening all four into the weakest of them.
    func testTheOtherCapabilitiesStillPromiseToNotice() {
        for capability in [Capability.microphone, .systemAudio] {
            XCTAssertTrue(
                PermissionGate.waitingCaption(for: capability).contains("I’ll notice"),
                "\(capability.rawValue) genuinely is noticed on the poll and should still say so")
        }
    }

    /// The stale-grant sentence must lead with the reopen. It used to open by asserting the grant
    /// had been dropped by an update or a re-sign and send the reader to toggle the switch — and on
    /// 16 August 2026 that was measured wrong on this Mac, where a plain relaunch restored capture
    /// with the switch untouched. Sending someone to re-toggle a switch that was never the problem
    /// is how this reads as "the app is broken".
    func testTheStaleGrantSentenceOffersTheReopenBeforeTheToggle() {
        let sentence = Permissions.staleGrantReason(subject: "Screen Recording", for: .screen)
        let reopen = sentence.localizedCaseInsensitiveContains("reopen")
        XCTAssertTrue(reopen, "the cheap, non-destructive remedy has to be in the sentence")

        guard let reopenAt = sentence.range(of: "eopen"),
            let toggleAt = sentence.range(of: "back on")
        else { return XCTFail("the sentence must carry both remedies: \(sentence)") }
        XCTAssertLessThan(
            reopenAt.lowerBound, toggleAt.lowerBound,
            "the remedy that works most of the time goes first; the record-rewriting one is the "
                + "fallback, not the opening instruction")
    }
}
