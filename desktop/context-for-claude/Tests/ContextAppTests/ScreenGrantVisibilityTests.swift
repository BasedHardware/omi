import XCTest

@testable import ContextApp

/// The minimum `PermissionAsking` these tests need: nothing is granted, no prompt is left, and
/// every pane opening is recorded. Its own rather than shared with `PermissionInvitationTests`,
/// whose recorder is file-private — and deliberately so: a fake that grows arms for every test that
/// borrows it stops being a statement of what *this* test assumes.
@MainActor
private final class ScreenAskRecorder: PermissionAsking {
    private(set) var settingsOpened: [Capability] = []

    func isGranted(_ capability: Capability) -> Bool { false }
    func request(_ capability: Capability) async -> Bool { false }
    func promptIsSpent(_ capability: Capability) -> Bool { true }
    func openSettings(for capability: Capability) { settingsOpened.append(capability) }
    func refresh(_ capability: Capability) async {}
    func materialiseSettingsRow(for capability: Capability) async {}
    var screenNeedsRelaunch: Bool { false }
}

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
            Permissions.screenRelaunchOfferWhenPreflightDenies(settingsWasOpened: true),
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
            Permissions.screenRelaunchOfferWhenPreflightDenies(settingsWasOpened: false),
            "a reopen offered before the user has been sent anywhere is a loop, not a remedy")
    }

    // MARK: - The reopen is bounded, recorded, and never offered for a record it cannot repair

    /// **The defect this file exists to stop shipping.**
    ///
    /// `screenNeedsRelaunch` is now armed by merely having opened the pane, which is the whole point
    /// — but it means an unbounded relaunch branch would restart the app forever for a user who
    /// declined. `OnboardingResume` faithfully returns them to this row, so the loop is two clicks
    /// wide and has no exit. The menu bar's row (`StatusView.handle`) has always spent exactly one
    /// reopen; the onboarding row must obey the same bound, or the fix is worse than the bug.
    @MainActor
    func testTheReopenIsSpentOnceAndThenBecomesThePane() {
        let asker = ScreenAskRecorder()
        var relaunches = 0
        let board = Self.board(asker, needsRelaunch: true, relaunch: { relaunches += 1 })

        XCTAssertTrue(board.invite(.screen))
        XCTAssertEqual(relaunches, 1, "the first click is the reopen the caption promises")

        XCTAssertTrue(board.invite(.screen))
        XCTAssertEqual(
            relaunches, 1,
            """
            the second click must not restart the app again: one reopen is the documented limit \
            (PermissionDeadEnd.relaunchLimit), and without the bound a user who never granted is \
            restarted every two clicks for as long as they keep trying
            """)
        XCTAssertEqual(
            asker.settingsOpened, [.screen],
            "once the reopen is spent the honest remainder is the pane, not silence")
    }

    /// A record no reopening can repair never gets even the first one. Both flags are true at once
    /// in that state, and reopening is known in advance not to help — `ScreenRepairControl` and the
    /// `tccutil` sentence are the real remedy there.
    @MainActor
    func testAnUnusableRecordIsNeverOfferedAReopen() {
        let asker = ScreenAskRecorder()
        var relaunches = 0
        let board = Self.board(
            asker, needsRelaunch: true, unusable: true, relaunch: { relaunches += 1 })

        XCTAssertTrue(board.invite(.screen))
        XCTAssertEqual(
            relaunches, 0,
            "reopening a process whose TCC record is unusable is a dead instruction the app can see "
                + "is dead before it gives it")
        XCTAssertEqual(asker.settingsOpened, [.screen])
    }

    /// The rows must stay live through the one episode that cannot end on its own — otherwise the
    /// caption asks for a click the card is refusing, which is the same shape of bug one layer up.
    @MainActor
    func testTheScreenRowStaysLiveWhileTheEpisodeCannotEnd() {
        let asker = ScreenAskRecorder()
        let live = Self.board(asker, needsRelaunch: true, relaunch: {})
        XCTAssertFalse(live.isBusy, "nothing is in flight yet, so nothing is busy")

        let quiet = Self.board(asker, needsRelaunch: false, relaunch: {})
        XCTAssertFalse(quiet.isBusy)
    }

    @MainActor
    private static func board(
        _ asker: ScreenAskRecorder,
        needsRelaunch: Bool,
        unusable: Bool = false,
        relaunch: @escaping @MainActor () -> Void
    ) -> PermissionInvitations {
        let broker = PermissionBroker()
        // A volatile suite: the relaunch tally is persisted, and a test that spent the real one
        // would change what the app offers the user who runs the suite.
        let defaults = UserDefaults(suiteName: "cfc.screen-grant-visibility.\(UUID().uuidString)")!
        return PermissionInvitations(
            granted: { asker.isGranted($0) },
            openSettings: { asker.openSettings(for: $0) },
            ledger: PermissionAskLedger(defaults: defaults),
            screenRecordIsUnusable: { unusable },
            screenNeedsRelaunch: { needsRelaunch },
            relaunch: relaunch,
            gate: {
                PermissionGate(
                    asking: asker, required: [$0], broker: broker,
                    leadIn: .zero, afterGrant: .zero, watchPoll: .zero)
            })
    }

    // MARK: - The word on the row

    /// **"Asking…" is the one word this state must never fall through to** — it is the reported bug,
    /// verbatim, and it is what a row says when something is still going to happen on its own.
    /// Nothing is: the poll cannot see this grant. The row is a button now, and it has to read like
    /// one.
    ///
    /// The two halves are deliberately different words. A definite stale grant keeps "Action
    /// required"; the case where the preflight merely denies us — where we do not know whether the
    /// user flipped anything — must not make that claim, but must still look like the control it is.
    func testTheScreenRowNeverSaysAskingOnceOnlyAReopenCanAnswerIt() {
        func word(granted: Bool) -> String {
            OnboardingView.statusWord(
                for: .screen, granted: granted, screenNeedsRelaunch: true,
                reported: true, asking: true, answer: nil, offered: false)
        }

        XCTAssertEqual(
            word(granted: false), "Reopen",
            "the reported dead end: a row reading \"Asking…\" while nothing was going to ask")
        XCTAssertEqual(
            word(granted: true), "Action required",
            "a grant TCC vouches for that this process cannot use is a definite state and keeps its "
                + "definite word")
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
