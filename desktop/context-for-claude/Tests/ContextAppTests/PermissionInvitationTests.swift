import XCTest

@testable import ContextApp

// MARK: - Nothing is asked until the user asks
//
//  The defect these were written for, verbatim: "the user gets no time to read what the window is
//  saying while asking for permissions. It should trigger asking permission when the user clicks on
//  the relevant section or button — it pops up the permission before the user can even read."
//
//  The permissions card used to start a run the instant it appeared, and the run walked all three
//  required capabilities back to back. The pacing inside each episode was real — 900 ms of lead-in,
//  1.1 s after the answer — and it was never the problem: the moment was chosen by a timer instead
//  of by the person reading. So the claim under test is not "the dialogs are further apart", it is
//  **a click is the only thing that raises one**, and the first test below is the one that fails
//  against the code that shipped.

/// A `PermissionAsking` that records what was asked of the system, and when.
///
/// Deliberately not shared with `OnboardingTests`' own recorder: that one is `private` to its file,
/// and this one has a different job — it is asked *whether* anything happened at all, rather than in
/// what order.
@MainActor
private final class AskRecorder: PermissionAsking {
    /// Capabilities that answer "granted" when the dialog is answered.
    var grants: Set<Capability> = []
    /// Capabilities already granted before anything is clicked.
    var alreadyGranted: Set<Capability> = []
    /// Capabilities whose TCC prompt macOS has already spent.
    var promptSpent: Set<Capability> = []
    /// A grant made by hand in System Settings, landing on the *n*th poll.
    var grantsAfterPolls: [Capability: Int] = [:]
    var screenNeedsRelaunch = false

    private(set) var asked: [Capability] = []
    private(set) var settingsOpened: [Capability] = []

    func isGranted(_ capability: Capability) -> Bool {
        if let remaining = grantsAfterPolls[capability] {
            if remaining <= 0 {
                grantsAfterPolls[capability] = nil
                alreadyGranted.insert(capability)
            } else {
                grantsAfterPolls[capability] = remaining - 1
            }
        }
        return alreadyGranted.contains(capability)
    }

    func request(_ capability: Capability) async -> Bool {
        asked.append(capability)
        await Task.yield()
        promptSpent.insert(capability)
        // Accessibility has no dialog at all: macOS grants it by hand, and the ask *is* the pane
        // opening. Modelled here because it is the capability the card's fourth row is for.
        if capability == .accessibility { settingsOpened.append(capability) }
        guard grants.contains(capability) else { return false }
        alreadyGranted.insert(capability)
        return true
    }

    func promptIsSpent(_ capability: Capability) -> Bool { promptSpent.contains(capability) }
    func openSettings(for capability: Capability) { settingsOpened.append(capability) }
    func refresh(_ capability: Capability) async {}

    /// Nothing was ever put in front of the user.
    var stayedQuiet: Bool { asked.isEmpty && settingsOpened.isEmpty }
}

final class PermissionInvitationTests: XCTestCase {

    /// The board at zero pacing, on its own broker so a test never touches the app-wide door. Every
    /// duration is zero: the pacing is asserted where it lives (`PermissionSequencingTests`), and
    /// what is under test here is *who starts an episode*, which no amount of waiting changes.
    @MainActor
    private func board(_ asker: AskRecorder) -> PermissionInvitations {
        let broker = PermissionBroker()
        return PermissionInvitations(
            granted: { asker.isGranted($0) },
            openSettings: { asker.openSettings(for: $0) },
            gate: {
                PermissionGate(
                    asking: asker, required: [$0], broker: broker,
                    leadIn: .zero, afterGrant: .zero, watchPoll: .zero)
            })
    }

    /// Lets whatever is in flight run until it reaches a state, without ever hanging the suite.
    /// Bounded by iterations rather than wall-clock so it stays hermetic on a loaded machine.
    @MainActor
    private func advance(
        until reached: () -> Bool, _ message: String,
        file: StaticString = #filePath, line: UInt = #line
    ) async {
        for _ in 0..<2_000 {
            if reached() { return }
            try? await Task.sleep(for: .milliseconds(1))
        }
        XCTFail(message, file: file, line: line)
    }

    /// Gives anything that *would* have started a chance to start. Long enough that a run with zero
    /// pacing would have raised all three dialogs several times over.
    @MainActor
    private func settle() async {
        for _ in 0..<50 { try? await Task.sleep(for: .milliseconds(1)) }
    }

    // MARK: The regression

    /// **The card appearing asks for nothing.**
    ///
    /// This is the test that fails against the code that shipped: `runSetup()` ran on `beginStep`,
    /// and with the pacing at zero every one of the three dialogs would be recorded here before the
    /// first `Task.sleep` returned.
    @MainActor
    func testNothingIsAskedUntilSomethingIsClicked() async {
        let asker = AskRecorder()
        asker.grants = [.microphone, .systemAudio, .screen]
        let board = self.board(asker)

        await settle()

        XCTAssertTrue(
            asker.stayedQuiet,
            "the permissions card asked macOS for \(asker.asked) and opened \(asker.settingsOpened) "
                + "without the user clicking anything — which is the whole of the defect")
        XCTAssertEqual(board.phase, .idle)
        XCTAssertFalse(board.canLeaveStep, "and nothing has been answered, so the card holds")
        board.cancel()
    }

    /// **A click asks for that capability and no other.** The other half of the same claim: the
    /// trigger is not merely late, it is scoped to the row that was pressed.
    @MainActor
    func testAClickAsksForThatCapabilityAndNothingElse() async {
        let asker = AskRecorder()
        asker.grants = [.screen]
        let board = self.board(asker)

        board.invite(.screen)
        await advance(until: { asker.asked.contains(.screen) }, "the click never reached macOS")
        await settle()

        XCTAssertEqual(asker.asked, [.screen])
        XCTAssertEqual(board.answers[.screen], .granted)
        XCTAssertNil(board.answers[.microphone], "the row nobody pressed was not asked about")
        XCTAssertNil(board.answers[.systemAudio])
        board.cancel()
    }

    /// A second click while an episode is in flight cannot stack a second dialog behind it.
    ///
    /// Queueing would be worse than refusing: the user would press a second row, see nothing happen,
    /// and meet its dialog minutes later with nothing on screen explaining what asked for it.
    @MainActor
    func testASecondClickCannotStackADialogBehindTheFirst() async {
        let asker = AskRecorder()  // nothing is granted, so the first click ends up waiting
        let board = self.board(asker)

        board.invite(.microphone)
        await advance(
            until: { board.postponing == .microphone },
            "the declined microphone should be waiting in System Settings")

        board.invite(.screen)
        await settle()

        XCTAssertFalse(
            asker.asked.contains(.screen),
            "a second row raised a dialog while the first was still unanswered")
        XCTAssertEqual(board.inFlight, .microphone)
        board.cancel()
    }

    // MARK: The legacy principal

    /// **A card entered with everything already granted can be left without clicking anything.**
    ///
    /// The principal nothing here had: an install over an existing install. macOS is still holding
    /// every grant from the previous copy, so the card draws four rows reading "Granted" — and the
    /// exit predicate used to quantify over answers the *gates* had recorded, which are only ever
    /// authored by a click. Nothing had been clicked, so nothing was answered, so Continue could
    /// never enable. Reported verbatim: "it knows i have granted all these and still does not allow
    /// me to continue."
    ///
    /// This fails against the shipped predicate — `required.allSatisfy { answers[$0] != nil }` over
    /// gate-recorded answers only — because no gate has run and every entry is nil.
    @MainActor
    func testACardEnteredFullyGrantedCanBeLeftWithoutClickingAnything() async {
        let asker = AskRecorder()
        asker.alreadyGranted = [.microphone, .systemAudio, .screen]
        let board = self.board(asker)

        await settle()

        XCTAssertTrue(
            board.canLeaveStep,
            "every required capability was granted before the card appeared and the only way off the "
                + "step was still a button that says the user will do them later")
        XCTAssertTrue(board.unanswered.isEmpty)
        XCTAssertTrue(
            asker.stayedQuiet,
            "and it must not have been earned by asking: the card asked macOS for \(asker.asked)")
        board.cancel()
    }

    /// The other half of the truth table, so the relaxation stays a relaxation and not a hole: a
    /// capability the system is *not* holding and nobody has clicked still shuts the card.
    @MainActor
    func testAPartlyGrantedCardStillHoldsOnTheOneThatIsMissing() async {
        let asker = AskRecorder()
        asker.alreadyGranted = [.microphone, .systemAudio]
        let board = self.board(asker)

        await settle()

        XCTAssertFalse(board.canLeaveStep, "screen recording was never granted and never answered")
        XCTAssertEqual(board.unanswered, [.screen])
        board.cancel()
    }

    /// "I'll do these later" must not answer *for* the user on something they already said yes to.
    ///
    /// The same fact drives both buttons, so fixing only the exit predicate would have left the
    /// card-wide skip writing "Later" over three live grants — a worse lie than the disabled button,
    /// because it is on record.
    @MainActor
    func testDeferringTheRestLeavesAGrantMadeBeforeTheCardAppeared() async {
        let asker = AskRecorder()
        asker.alreadyGranted = [.microphone, .systemAudio]
        let board = self.board(asker)

        board.deferRest()

        XCTAssertEqual(board.answers[.microphone], .granted, "a pre-existing grant is not a skip")
        XCTAssertEqual(board.answers[.systemAudio], .granted)
        XCTAssertEqual(board.answers[.screen], .deferred, "and only the missing one is deferred")
        XCTAssertTrue(board.canLeaveStep)
        board.cancel()
    }

    // MARK: Leaving the card

    /// **The exit predicate is unchanged**: every required capability answered, by the user. Only the
    /// route to those answers changed.
    @MainActor
    func testTheCardHoldsUntilEveryRequiredCapabilityIsAnswered() async {
        let asker = AskRecorder()
        asker.grants = [.microphone, .systemAudio]
        let board = self.board(asker)

        for capability in [Capability.microphone, .systemAudio] {
            board.invite(capability)
            // Both halves matter: the answer lands inside the episode, and `inFlight` clears only
            // when the episode returns — so waiting on the answer alone would race the next click
            // against the refusal that keeps two dialogs from overlapping.
            await advance(
                until: { board.answers[capability] == .granted && board.inFlight == nil },
                "\(capability.rawValue) never landed")
        }
        XCTAssertFalse(board.canLeaveStep, "screen recording is still unanswered")

        board.invite(.screen)
        await advance(
            until: { board.postponing == .screen }, "the declined screen row should be waiting")
        board.postpone(.screen)
        await advance(until: { board.canLeaveStep }, "an explicit deferral is a terminal answer")

        XCTAssertEqual(board.answers[.screen], .deferred)
        board.cancel()
    }

    /// **The dead end nothing-is-automatic would otherwise create.**
    ///
    /// The per-capability escape only exists once an episode has reached System Settings, so a user
    /// who clicks nothing at all had no answer to give and no way forward. "I'll do these later"
    /// answers everything outstanding — and only what is outstanding.
    @MainActor
    func testDeferringTheRestAnswersEverythingOutstandingAndNothingElse() async {
        let asker = AskRecorder()
        asker.grants = [.microphone]
        let board = self.board(asker)

        board.invite(.microphone)
        await advance(
            until: { board.answers[.microphone] == .granted && board.inFlight == nil },
            "the microphone never landed")

        board.deferRest()

        XCTAssertEqual(board.answers[.microphone], .granted, "a grant is not overwritten by a skip")
        XCTAssertEqual(board.answers[.systemAudio], .deferred)
        XCTAssertEqual(board.answers[.screen], .deferred)
        XCTAssertNil(
            board.answers[.accessibility],
            "window text is not required, so skipping the required ones does not answer for it")
        XCTAssertTrue(board.canLeaveStep)
        board.cancel()
    }

    /// It is refused while an episode is in flight: that episode has its own escape on screen, and
    /// two escapes offering different scopes at once is a choice nobody can make correctly.
    @MainActor
    func testTheCardWideEscapeIsRefusedWhileAnEpisodeIsInFlight() async {
        let asker = AskRecorder()
        let board = self.board(asker)

        board.invite(.microphone)
        await advance(until: { board.postponing == .microphone }, "expected a wait in settings")

        board.deferRest()
        XCTAssertNil(board.answers[.screen], "the card-wide skip must not fire under a live episode")
        board.cancel()
    }

    // MARK: The second click

    /// TCC shows each prompt exactly once, so a second click on a capability that already has an
    /// answer can only open the pane. Asking again does nothing at all and the row looks dead.
    @MainActor
    func testASecondClickOnAnAnsweredRowOpensThePaneRatherThanReAsking() async {
        let asker = AskRecorder()
        let board = self.board(asker)

        board.invite(.microphone)
        await advance(until: { board.postponing == .microphone }, "expected a wait in settings")
        board.postpone(.microphone)
        await advance(until: { board.inFlight == nil }, "the postponed episode never ended")

        let openedBefore = asker.settingsOpened.count
        board.invite(.microphone)
        await settle()

        XCTAssertEqual(
            asker.asked.filter { $0 == .microphone }.count, 1,
            "macOS was asked a second time for a prompt it has already spent")
        XCTAssertGreaterThan(
            asker.settingsOpened.count, openedBefore,
            "the only route left after an answer is the pane, and the row has to take it")
        board.cancel()
    }

    /// A row that is already granted is not an ask. Re-running its episode would put a beat of
    /// "Asking…" through a checkmark for nothing.
    @MainActor
    func testAGrantedRowIsNotAskedAgain() async {
        let asker = AskRecorder()
        asker.alreadyGranted = [.microphone]
        let board = self.board(asker)

        board.invite(.microphone)
        await settle()

        XCTAssertTrue(asker.stayedQuiet, "a granted row asked macOS for \(asker.asked)")
        board.cancel()
    }

    // MARK: Window text

    /// **Clicking the fourth row is what opens the pane, and the wait it lands in is what asks for
    /// the overlay.**
    ///
    /// This row used to be reachable only through a "Show me the row" panel on our own card: a
    /// rehearsal of the instruction, behind a button, before the instruction. Now it is a row like
    /// the other three, and `PermissionGate.spotlightSubject` — the one predicate that decides
    /// whether anything is pointing — answers for it without a button being pressed.
    @MainActor
    func testClickingWindowTextOpensThePaneAndAsksForTheOverlay() async {
        let asker = AskRecorder()
        let board = self.board(asker)

        board.invite(.accessibility)
        await advance(
            until: { board.postponing == .accessibility },
            "window text has no dialog, so its episode must end up waiting in System Settings")

        XCTAssertTrue(asker.settingsOpened.contains(.accessibility))
        XCTAssertEqual(
            PermissionGate.spotlightSubject(of: board.phase), .accessibility,
            "the pane is open and nothing is pointing at the row — which is the state the overlay "
                + "exists for")
        board.cancel()
    }

    /// Listed, offered, never required. Gating the card on a grant macOS refuses to prompt for would
    /// strand anybody unwilling to leave the flow.
    @MainActor
    func testWindowTextIsOfferedButNeverHoldsTheCard() async {
        let asker = AskRecorder()
        asker.grants = [.microphone, .systemAudio, .screen]
        let board = self.board(asker)

        XCTAssertTrue(board.listed.contains(.accessibility))
        XCTAssertFalse(board.required.contains(.accessibility))

        for capability in board.required {
            board.invite(capability)
            await advance(
                until: { board.answers[capability] == .granted && board.inFlight == nil },
                "\(capability.rawValue) never landed")
        }
        XCTAssertTrue(
            board.canLeaveStep, "the three required grants are in and window text must not block")
        board.cancel()
    }

    // MARK: Leaving

    /// The watch in System Settings is unbounded by design, so leaving the card is the only thing
    /// that can end it. A board that kept polling after onboarding moved on would hold the broker
    /// shut against every other consent surface in the app.
    @MainActor
    func testLeavingTheCardEndsEveryWatch() async {
        let asker = AskRecorder()
        let board = self.board(asker)

        board.invite(.screen)
        await advance(until: { board.postponing == .screen }, "expected a wait in settings")

        board.cancel()
        XCTAssertNil(board.inFlight)
        XCTAssertFalse(board.isBusy)
    }

    /// A grant made by hand in System Settings still lands with no deadline — the click starts the
    /// watch, and only the grant or the escape ends it.
    @MainActor
    func testAGrantMadeInSettingsAfterAClickIsStillObserved() async {
        let asker = AskRecorder()
        asker.grantsAfterPolls = [.screen: 6]
        let board = self.board(asker)

        board.invite(.screen)
        await advance(
            until: { board.answers[.screen] == .granted },
            "a grant flipped in System Settings after several polls was never noticed")
        board.cancel()
    }
}
