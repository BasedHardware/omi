import XCTest

@testable import ContextApp

/// **A permission flow that can be walked twice with no change and no new information.**
///
/// The state these were written for is real and was live on a user's Mac. This app was re-released
/// under a notarized Developer ID identity where it had been ad-hoc signed, and `tccd` kept matching
/// incoming requests against the code requirement the *old* build wrote:
///
/// ```
/// tccd: Failed to match existing code requirement for subject com.omi.context-for-claude
///       and service kTCCServiceScreenCapture
/// ```
///
/// So the switch in System Settings reads **on**, the user grants it again, and the grant is inert.
/// Every surface in the flow answered that by repeating itself: the onboarding card sat in
/// `waitingInSettings` saying "switch it on and I'll notice" forever, the closing card offered
/// "Open Screen Recording" and no other button at all, and the menu bar's Screen row ended and
/// reopened the whole app on every single tap.
///
/// The claim under test is a bound on repetition, not a diagnosis: **the same dead instruction is
/// never shown a third time, and the way out stays reachable throughout.** The assertions are on the
/// distinguishing behaviour — which control the card offers, whether the pane is reopened, whether
/// the process is ended again — and on sentences *differing*, never on their wording.
final class PermissionDeadEndTests: XCTestCase {

    /// A private domain per test, so nothing here reads or writes the app's own tally.
    private func ledger(_ name: String = #function) -> PermissionAskLedger {
        let suite = "context.tests.deadend.\(name).\(UUID().uuidString)"
        guard let defaults = UserDefaults(suiteName: suite) else {
            XCTFail("could not open a private defaults domain")
            return PermissionAskLedger()
        }
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }
        return PermissionAskLedger(defaults: defaults)
    }

    // MARK: - The rule

    /// The bar itself. Two asks are allowed; the third presentation has to be a different one.
    func testTheThirdPresentationIsNeverTheSameInstruction() {
        XCTAssertFalse(PermissionDeadEnd.asksAreSpent(0))
        XCTAssertFalse(
            PermissionDeadEnd.asksAreSpent(1),
            "one fruitless ask is a user who was merely slow, not a flow that is stuck")
        XCTAssertTrue(
            PermissionDeadEnd.asksAreSpent(2),
            "after two the next thing on screen is the third, and it may not be the same")
    }

    /// A restart gets **one** attempt, and fewer than a pane does. Reopening the pane costs a click;
    /// reopening the app ends the process the user is reading the instruction in.
    func testARestartIsOfferedOnceAndThenNeverAgain() {
        XCTAssertTrue(PermissionDeadEnd.mayRelaunch(after: 0))
        XCTAssertFalse(
            PermissionDeadEnd.mayRelaunch(after: 1),
            "the relaunch happened and the capability is still refused, so it did not help")
        XCTAssertLessThan(PermissionDeadEnd.relaunchLimit, PermissionDeadEnd.askLimit)
    }

    /// **The subtlety the whole loop hangs on.** `CGPreflightScreenCaptureAccess()` reads true for a
    /// process the window server is refusing outright, so a tally cleared on the TCC record alone
    /// would be cleared on every poll of exactly the state it exists to bound.
    func testATccRecordIsNotProofTheScreenIsWorking() {
        XCTAssertFalse(
            PermissionDeadEnd.isWorking(.screen, granted: true, screenNeedsRelaunch: true),
            "a granted record over a refused process is the state that rearms the restart loop")
        XCTAssertTrue(PermissionDeadEnd.isWorking(.screen, granted: true, screenNeedsRelaunch: false))
        XCTAssertFalse(PermissionDeadEnd.isWorking(.screen, granted: false, screenNeedsRelaunch: false))
        XCTAssertTrue(
            PermissionDeadEnd.isWorking(.microphone, granted: true, screenNeedsRelaunch: true),
            "the relaunch is the screen's alone; it may not hold the other three's tallies open")
    }

    /// The two dead ends say different things, because two different instructions failed. Asserted as
    /// a difference rather than as wording — the point is that the user is not read the same line.
    func testTheSentenceAfterAReopenIsNotTheSentenceBeforeIt() {
        for capability in Capability.allCases {
            XCTAssertNotEqual(
                PermissionDeadEnd.sentence(for: capability, reopened: true),
                PermissionDeadEnd.sentence(for: capability, reopened: false))
        }
    }

    /// The remedy is the one that rewrites the TCC record against this build's signature, and it is
    /// the same remedy `Permissions.staleGrantReason` names — two surfaces telling a user to do two
    /// different things about one `tccd` mismatch is the defect one level up.
    func testTheRemedyIsToRecreateTheRecordRatherThanToSwitchItOnAgain() {
        for capability in Capability.allCases {
            for reopened in [true, false] {
                let sentence = PermissionDeadEnd.sentence(for: capability, reopened: reopened)
                    .lowercased()
                XCTAssertTrue(
                    sentence.contains("off and back on"),
                    "\(capability) is still being told to do the thing that already failed")
                XCTAssertFalse(sentence.contains("switch it on"))
                XCTAssertTrue(
                    sentence.contains(capability.settingsLocation.lowercased()),
                    "the sentence is read when nothing is opening the pane, so it has to say where")
            }
        }
    }

    /// It claims nothing about *why*. The app cannot tell a stale code requirement from a user who
    /// never flipped the switch, and a sentence that picks one is a sentence that is wrong for the
    /// other — which on this card is most people.
    func testTheSentenceDoesNotDiagnoseACauseItCannotSee() {
        let sentence = PermissionDeadEnd.sentence(for: .accessibility, reopened: false).lowercased()
        XCTAssertFalse(sentence.contains("re-sign"))
        XCTAssertFalse(sentence.contains("signature"))
        XCTAssertTrue(
            sentence.contains("if the switch"),
            "the remedy has to be conditional on what the user can actually see")
    }

    // MARK: - The tally

    func testATallyOnlySpendsOnAsksAndOnlyClearsOnSomethingThatWorks() {
        let ledger = self.ledger()

        XCTAssertEqual(ledger.asks(.screen), 0)
        ledger.noteAsked(.screen)
        ledger.noteAsked(.screen)
        XCTAssertTrue(PermissionDeadEnd.asksAreSpent(ledger.asks(.screen)))
        XCTAssertEqual(ledger.asks(.microphone), 0, "one capability's dead end is not another's")

        ledger.noteWorking(.screen)
        XCTAssertFalse(
            PermissionDeadEnd.asksAreSpent(ledger.asks(.screen)),
            "the grant landed, so a later honest ask starts from zero rather than inheriting this")
    }

    /// The tally has to survive the very remedy it bounds: "reopen me" ends this process, so a
    /// counter that lived in memory would come back at zero and offer the restart again.
    func testTheTallySurvivesTheRelaunchItIsCounting() {
        let suite = "context.tests.deadend.relaunch.\(UUID().uuidString)"
        guard let defaults = UserDefaults(suiteName: suite) else {
            return XCTFail("could not open a private defaults domain")
        }
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }

        PermissionAskLedger(defaults: defaults).noteRelaunched(.screen)

        // A fresh ledger over the same store is what the successor process holds.
        let successor = PermissionAskLedger(defaults: defaults)
        XCTAssertFalse(
            PermissionDeadEnd.mayRelaunch(after: successor.relaunches(.screen)),
            "the app reopened itself and is still refused; offering the same restart is the loop")
    }

    // MARK: - The line a glance surface adds

    func testNothingIsSaidWhileAskingAgainIsStillWorthSomething() {
        XCTAssertNil(
            PermissionDeadEnd.note(
                for: Capability.allCases, granted: { _ in false }, screenNeedsRelaunch: false,
                asks: { _ in 1 }, relaunches: { _ in 0 }),
            "one fruitless ask is not a dead end, and saying so would be the app giving up early")
        XCTAssertNil(
            PermissionDeadEnd.note(
                for: Capability.allCases, granted: { _ in true }, screenNeedsRelaunch: false,
                asks: { _ in 9 }, relaunches: { _ in 9 }),
            "everything works, so there is nothing to be stuck on however the tally reads")
    }

    func testASpentAskIsReportedAndAReopenOutranksIt() {
        let spent = PermissionDeadEnd.note(
            for: [.microphone], granted: { _ in false }, screenNeedsRelaunch: false,
            asks: { _ in 2 }, relaunches: { _ in 0 })
        XCTAssertEqual(spent, PermissionDeadEnd.sentence(for: .microphone, reopened: false))

        let reopened = PermissionDeadEnd.note(
            for: [.screen], granted: { _ in true }, screenNeedsRelaunch: true,
            asks: { _ in 0 }, relaunches: { _ in 1 })
        XCTAssertEqual(
            reopened, PermissionDeadEnd.sentence(for: .screen, reopened: true),
            "a granted-but-refused screen after a spent reopen is the reported state exactly")
    }
}

// MARK: - The repair the app hands over and must not perform

/// **The one screen state whose remedy is a Terminal command, and the control that hands it over.**
///
/// `Permissions.ScreenBlock.recordUnusable` is the state where this process started *holding* the
/// Screen Recording grant and macOS refused it anyway. Reopening cannot help — window-server capture
/// rights are settled when a process connects, and the successor connects the same way — and the app
/// has already told this user to reopen. Deleting the TCC record is the only thing left, and the app
/// may not do that for them: the detection is an inference rather than a reading of TCC's stored
/// requirement, so a false positive would destroy a working consent record, and an app that resets
/// its own TCC records to re-prompt is indistinguishable from consent-fatigue farming.
///
/// So the control copies the command and stops there. These hold it to *only* that state, and to the
/// command the guidance actually names.
final class PermissionRepairCommandTests: XCTestCase {

    /// **The states with a working remedy keep it.** A Terminal command in place of a click would be
    /// this app sending somebody to a shell over a switch — a worse failure than the one being fixed.
    func testOnlyAnUnusableRecordIsOfferedACommand() {
        for block in [
            Permissions.ScreenBlock.notGranted, .grantLost, .needsRelaunch,
        ] {
            XCTAssertNil(
                ScreenRepairControl.of(block, copied: false),
                "\(block) has a remedy the user can click; offering `tccutil` instead abandons it")
        }
        XCTAssertNil(
            ScreenRepairControl.of(nil, copied: false),
            "nothing is in the way at all, so there is nothing to repair")
        XCTAssertNotNil(ScreenRepairControl.of(.recordUnusable, copied: false))
    }

    /// **The command the control copies is the command the guidance names.** Two spellings of one
    /// `tccutil` invocation is how a bundle id in a sentence drifts from the one on the clipboard,
    /// and the user cannot tell which of the two is wrong.
    func testTheCopiedCommandIsTheOneTheGuidanceNames() {
        guard let control = ScreenRepairControl.of(.recordUnusable, copied: false) else {
            return XCTFail("the state that needs the command must offer it")
        }
        XCTAssertTrue(
            Permissions.ScreenBlock.recordUnusable.reason.contains(control.command),
            "the sentence tells the user to run something the button does not put on their clipboard")
        XCTAssertTrue(
            control.command.contains("tccutil reset ScreenCapture"),
            "and it is the screen record being deleted, not some other service")
    }

    /// The press has to say it landed, and then stop saying it — the popover's own idiom, where the
    /// connector button's label carries the state rather than a toast or a second colour.
    func testThePressConfirmsItselfAndThenGoesBackToBeingAnOffer() {
        let offered = ScreenRepairControl.of(.recordUnusable, copied: false)
        let confirmed = ScreenRepairControl.of(.recordUnusable, copied: true)

        XCTAssertNotEqual(
            offered?.action, confirmed?.action,
            "a copy that looks identical to no copy is a control the user presses again")
        XCTAssertEqual(
            offered?.command, confirmed?.command,
            "and the confirmation changes nothing about what would be copied")
    }

    /// The note is the popover's, not the engine's. `ScreenBlock.reason` is already on this surface
    /// as the paused line, and 320 pt of it twice is the whole panel.
    func testTheControlsOwnNoteIsShorterThanTheFullGuidance() {
        guard let control = ScreenRepairControl.of(.recordUnusable, copied: false) else {
            return XCTFail("the state that needs the command must offer it")
        }
        XCTAssertLessThan(
            control.note.count, Permissions.ScreenBlock.recordUnusable.reason.count,
            "the row's line is a lead-in to a button, not a second copy of the paused line")
    }

    // MARK: The loop exits reach this row rather than repeating

    /// **The bound on repetition must not repeat a *different* dead instruction.** An unusable record
    /// cannot be repaired from the pane, so "turn it off and back on, then reopen me" is as dead as
    /// "switch it on" was — and this is the sentence the flow's own dead end has to defer to.
    func testTheFlowsDeadEndDefersToTheCommandForAnUnusableRecord() {
        XCTAssertEqual(
            PermissionDeadEnd.sentence(for: .screen, reopened: true, screenRecordIsUnusable: true),
            Permissions.ScreenBlock.recordUnusable.reason,
            "one sentence names what actually works, and every surface reads that one")
        XCTAssertNotEqual(
            PermissionDeadEnd.sentence(for: .screen, reopened: true, screenRecordIsUnusable: true),
            PermissionDeadEnd.sentence(for: .screen, reopened: true))
        XCTAssertEqual(
            PermissionDeadEnd.sentence(
                for: .microphone, reopened: false, screenRecordIsUnusable: true),
            PermissionDeadEnd.sentence(for: .microphone, reopened: false),
            "the screen's record says nothing about the microphone's")
    }

    /// And the popover says one thing about one row: the control carries a note *and* a press, so the
    /// words-only line stands down rather than arguing with it.
    func testThePopoverDoesNotSayTwoThingsAboutOneRow() {
        XCTAssertNil(
            PermissionDeadEnd.note(
                for: [.screen], granted: { _ in true }, screenNeedsRelaunch: true,
                screenRecordIsUnusable: true, asks: { _ in 5 }, relaunches: { _ in 5 }),
            "the repair control owns this row; a second sentence under it is the loop in a new costume")
        XCTAssertNotNil(
            PermissionDeadEnd.note(
                for: [.microphone], granted: { _ in false }, screenNeedsRelaunch: true,
                screenRecordIsUnusable: true, asks: { _ in 5 }, relaunches: { _ in 0 }),
            "and every other row still reports its own dead end")
    }

    /// **A restart is withheld on the first press, not the second.** `screenNeedsRelaunch` is true in
    /// this state as well — an unusable record is also a stale grant — so a card that consulted only
    /// the tally would offer one reopen before learning what `Permissions` already knew.
    func testAnUnusableRecordIsNeverOfferedARestartAtAll() {
        let finale = OnboardingFinale.of(
            screenGranted: true, needsRelaunch: true, screenWasPostponed: false,
            screenRecordIsUnusable: true)

        XCTAssertEqual(
            finale.action, .close,
            "reopening is known in advance not to help, so it may not be offered even once")
        XCTAssertTrue(finale.askIsSpent, "and the copy says what does work instead")
    }
}

// MARK: - The closing card

/// The `.done` card's own dead end, which is the one with no door in it.
///
/// `OnboardingFinaleTests` already covers the stranding this flow fixed once — a postponed run whose
/// only button reopened a pane. This is the second one: an *undecided* run whose grant does not take.
/// The card offers "Open Screen Recording" and nothing else, so pressing it is the only thing the
/// user can do, and pressing it changes nothing.
final class OnboardingFinaleDeadEndTests: XCTestCase {

    /// The trap. Against the shipped value this fails: the action stays `.openScreenRecording`
    /// however many times the pane has been opened, so there is never a button that closes the card.
    func testACardThatHasSpentItsAsksOffersTheDoorRatherThanThePaneAgain() {
        let finale = OnboardingFinale.of(
            screenGranted: false, needsRelaunch: false, screenWasPostponed: false,
            askIsSpent: true)

        XCTAssertEqual(
            finale.action, .close,
            "the pane has been opened twice for nothing — a third press is the same dead instruction "
                + "and there is no other control on this card")
        XCTAssertFalse(
            finale.opensThePane,
            "and the card must not reopen it on arrival either, which is the same instruction "
                + "delivered without even a press")
        XCTAssertTrue(
            finale.watchesForTheGrant,
            "a switch flipped by hand still has to reach the card; giving up asking is not giving "
                + "up noticing")
        XCTAssertTrue(finale.askIsSpent, "and the copy has to be able to say something else")
    }

    /// The relaunch half. macOS relatches `screenNeedsRelaunch` on the successor's first refused
    /// capture, so before this the button came back saying "Restart to finish" after every restart.
    func testARestartThatDidNotHelpIsNotOfferedASecondTime() {
        let again = OnboardingFinale.of(
            screenGranted: true, needsRelaunch: true, screenWasPostponed: false,
            relaunchIsSpent: true)

        XCTAssertEqual(
            again.action, .close,
            "the app has already been reopened for this grant and is still refused")
        XCTAssertTrue(again.askIsSpent)
        XCTAssertEqual(
            OnboardingFinale.of(
                screenGranted: true, needsRelaunch: true, screenWasPostponed: false
            ).action, .restart,
            "and the first restart is still offered — a grant that landed after launch really does "
                + "need one")
    }

    /// The bound is on repetition, not on helping. Nothing changes for a run that has not spent
    /// anything, which is every ordinary first run.
    func testAnOrdinaryRunIsUntouched() {
        XCTAssertEqual(
            OnboardingFinale.of(
                screenGranted: false, needsRelaunch: false, screenWasPostponed: false),
            OnboardingFinale(
                action: .openScreenRecording, watchesForTheGrant: true, opensThePane: true,
                ringsTheMenuBar: false, askIsSpent: false))
    }
}

// MARK: - The onboarding card

/// **The permissions card's own loop, and the escape that has to survive it.**
///
/// The card polls `waitingInSettings` twice a second with no deadline, which is right: the grant is
/// the thing being waited on. What was wrong is that the sentence over it never changed, so a user
/// whose grant does not take reads "System Settings is open on the right row. Switch it on and I'll
/// notice" for as long as they are willing to keep trying.
final class PermissionsCardDeadEndTests: XCTestCase {

    /// A `PermissionAsking` that never grants anything — the machine the user in the report is on.
    @MainActor
    private final class RefusingAsker: PermissionAsking {
        var promptSpent: Set<Capability> = []
        private(set) var settingsOpened: [Capability] = []
        var screenNeedsRelaunch = false

        func isGranted(_ capability: Capability) -> Bool { false }
        func request(_ capability: Capability) async -> Bool {
            promptSpent.insert(capability)
            return false
        }
        func promptIsSpent(_ capability: Capability) -> Bool { promptSpent.contains(capability) }
        func openSettings(for capability: Capability) { settingsOpened.append(capability) }
        func refresh(_ capability: Capability) async {}
    }

    @MainActor
    private func board(
        _ asker: RefusingAsker, ledger: PermissionAskLedger, recordIsUnusable: Bool = false
    ) -> PermissionInvitations {
        let broker = PermissionBroker()
        return PermissionInvitations(
            granted: { asker.isGranted($0) },
            openSettings: { asker.openSettings(for: $0) },
            ledger: ledger,
            screenRecordIsUnusable: { recordIsUnusable },
            gate: {
                PermissionGate(
                    asking: asker, required: [$0], broker: broker,
                    leadIn: .zero, afterGrant: .zero, watchPoll: .zero)
            })
    }

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

    private func privateLedger() -> PermissionAskLedger {
        let suite = "context.tests.deadend.card.\(UUID().uuidString)"
        guard let defaults = UserDefaults(suiteName: suite) else {
            XCTFail("could not open a private defaults domain")
            return PermissionAskLedger()
        }
        addTeardownBlock { UserDefaults.standard.removePersistentDomain(forName: suite) }
        return PermissionAskLedger(defaults: defaults)
    }

    /// **The regression.** Two clicks on a row that never grants, and the card must not be saying the
    /// same thing it said after the first.
    @MainActor
    func testTheCardStopsRepeatingAnInstructionThatIsNotWorking() async {
        let asker = RefusingAsker()
        let board = self.board(asker, ledger: privateLedger())

        board.invite(.screen)
        await advance(until: { board.postponing == .screen }, "expected a wait in System Settings")
        let firstTime = board.caption
        XCTAssertNotNil(firstTime, "the gate says where the user is standing")

        board.postpone(.screen)
        await advance(until: { board.inFlight == nil }, "the postponed episode never ended")
        board.invite(.screen)

        // Both halves, because the shipped card fails the second one by *saying nothing at all*: the
        // re-click takes `invite`'s open-the-pane branch, which sets nothing in flight, so the
        // caption goes nil and a bare inequality would pass over a silently reopened pane.
        XCTAssertNotEqual(
            board.caption, firstTime,
            "the user has been sent to the pane twice and the switch is still not ours; the card "
                + "repeating itself is what reads as the app being broken")
        XCTAssertEqual(board.caption, PermissionDeadEnd.sentence(for: .screen, reopened: false))
        board.cancel()
    }

    /// The half that keeps the bound from becoming a gag: a first click still gets the ordinary
    /// instruction, because a user who has not been anywhere yet has nothing to be stuck on.
    @MainActor
    func testAFirstClickStillGetsTheOrdinaryInstruction() async {
        let asker = RefusingAsker()
        let board = self.board(asker, ledger: privateLedger())

        board.invite(.microphone)
        await advance(until: { board.postponing == .microphone }, "expected a wait in settings")

        XCTAssertNil(board.deadEnd, "one ask is not a dead end")
        board.cancel()
    }

    /// **An unusable record does not have to be walked into twice.** `Permissions` already knows the
    /// pane cannot repair it, so the very first click says what works rather than spending two trips
    /// to learn something the app was told at launch.
    @MainActor
    func testAnUnusableRecordSaysTheTrueThingOnTheFirstClick() async {
        let asker = RefusingAsker()
        let board = self.board(asker, ledger: privateLedger(), recordIsUnusable: true)

        board.invite(.screen)
        await advance(until: { board.postponing == .screen }, "expected a wait in settings")

        XCTAssertEqual(board.caption, Permissions.ScreenBlock.recordUnusable.reason)
        XCTAssertNotEqual(
            board.deadEnd, PermissionDeadEnd.sentence(for: .screen, reopened: false),
            "and it is not the off-and-back-on sentence, which cannot repair this record either")
        board.cancel()
    }

    /// **"I'll do this later" has to keep working in the unwinnable state.** It is the only thing
    /// other than a grant that ends the wait, and a card whose escape depended on the grant landing
    /// would be the trap the escape exists to prevent, one level down.
    @MainActor
    func testTheEscapeStaysReachableAfterTheAskIsSpent() async {
        let asker = RefusingAsker()
        let ledger = privateLedger()
        for _ in 0..<PermissionDeadEnd.askLimit { ledger.noteAsked(.screen) }
        let board = self.board(asker, ledger: ledger)

        board.invite(.screen)
        await advance(
            until: { board.postponing == .screen },
            "the per-row escape has to be on screen even once the ask is spent")
        XCTAssertNotNil(board.deadEnd, "and it is offered under a sentence that is not the old one")

        board.postpone(.screen)
        XCTAssertEqual(board.answers[.screen], .deferred)
        board.cancel()
    }

    /// And the card-wide escape, from the state where every required row is unwinnable: the user
    /// finishes onboarding with a partly-capturing app rather than being held on the card.
    @MainActor
    func testTheCardCanBeLeftWhenEveryRequiredCapabilityIsUnwinnable() async {
        let asker = RefusingAsker()
        let ledger = privateLedger()
        for capability in [Capability.microphone, .systemAudio, .screen] {
            for _ in 0..<PermissionDeadEnd.askLimit { ledger.noteAsked(capability) }
        }
        let board = self.board(asker, ledger: ledger)

        board.deferRest()

        XCTAssertTrue(
            board.canLeaveStep,
            "nothing here can ever be granted, so the only way off the card is the deliberate one — "
                + "and it has to still be there")
        XCTAssertNil(board.deadEnd, "an answered card is not still reporting an unmet ask")
        board.cancel()
    }
}
