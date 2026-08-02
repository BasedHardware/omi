import AppKit
import XCTest

@testable import ContextApp

// MARK: - The step machine

/// The ordering, the skip and the back button.
///
/// These are pure functions on `OnboardingStep` precisely so they can be asserted: the order the
/// cards come in is a product decision with a wrong answer available — asking macOS for a microphone
/// before the account those recordings land in is known — and a `View` is not a place a decision like
/// that can be tested.
final class OnboardingStepMachineTests: XCTestCase {

    /// The spec's order, `docs/first-run-experience.md` Phase 4: welcome → value → sign in →
    /// permissions → connectors → tutorial intro.
    ///
    /// Sign-in before permissions is the load-bearing part. Everything this app records lands in an
    /// Omi account, the permissions are what start the recording, so the account has to be known
    /// first. The connector is local configuration and can wait; consent cannot.
    func testTheItineraryFollowsTheSpecOrder() {
        XCTAssertEqual(
            OnboardingStep.itinerary(signedIn: false),
            [.welcome, .value, .signIn, .permissions, .connector, .tutorial, .done])
    }

    /// A restored session skips the sign-in card and nothing else, which is what keeps a reinstall
    /// one click.
    func testARestoredSessionSkipsSignInAndOnlySignIn() {
        let itinerary = OnboardingStep.itinerary(signedIn: true)
        XCTAssertEqual(itinerary, [.welcome, .value, .permissions, .connector, .tutorial, .done])
        XCTAssertFalse(itinerary.contains(.signIn))
        XCTAssertEqual(OnboardingStep.next(after: .value, signedIn: true), .permissions)
    }

    func testNextWalksTheItineraryAndEndsAtDone() {
        for signedIn in [true, false] {
            let itinerary = OnboardingStep.itinerary(signedIn: signedIn)
            for (index, step) in itinerary.enumerated() where index + 1 < itinerary.count {
                XCTAssertEqual(
                    OnboardingStep.next(after: step, signedIn: signedIn),
                    itinerary[index + 1],
                    "after \(step), signedIn: \(signedIn)")
            }
            XCTAssertNil(
                OnboardingStep.next(after: .done, signedIn: signedIn),
                "the flow has to end; a next step after .done would loop the finale")
        }
    }

    /// Back exists only while nothing irreversible has happened.
    ///
    /// From `.permissions` onward there is nothing to go back to: macOS shows each TCC prompt exactly
    /// once and will not un-ask, so a card reached by "back" could not do anything. A button that
    /// cannot work is worse than no button, which is why these are nil rather than best-effort.
    func testBackIsOfferedOnlyBeforeAnythingIrreversibleHasHappened() {
        XCTAssertNil(OnboardingStep.back(from: .welcome, signedIn: false), "nothing precedes welcome")
        XCTAssertEqual(OnboardingStep.back(from: .value, signedIn: false), .welcome)
        XCTAssertEqual(OnboardingStep.back(from: .signIn, signedIn: false), .value)

        for step: OnboardingStep in [.permissions, .connector, .tutorial, .done] {
            XCTAssertNil(
                OnboardingStep.back(from: step, signedIn: false),
                "\(step) is past the point where anything can be un-asked")
        }
    }

    /// A skipped card is not a card you can reach backwards either.
    func testBackNeverLandsOnACardTheItinerarySkipped() {
        XCTAssertNil(OnboardingStep.back(from: .signIn, signedIn: true))
        for signedIn in [true, false] {
            let itinerary = Set(OnboardingStep.itinerary(signedIn: signedIn))
            for step in OnboardingStep.allCases {
                guard let target = OnboardingStep.back(from: step, signedIn: signedIn) else { continue }
                XCTAssertTrue(itinerary.contains(target), "back from \(step) reached a skipped card")
            }
        }
    }

    /// The dots count work, not screens: the welcome card is before the flow starts and `.done` is
    /// after it ends.
    func testProgressDotsCountOnlyTheCardsOfActualWork() {
        XCTAssertEqual(
            OnboardingStep.progressSteps(signedIn: false),
            [.value, .signIn, .permissions, .connector, .tutorial])
        XCTAssertEqual(OnboardingStep.progressSteps(signedIn: true).count, 4)

        XCTAssertNil(OnboardingStep.progressIndex(of: .welcome, signedIn: false))
        XCTAssertNil(OnboardingStep.progressIndex(of: .done, signedIn: false))
        XCTAssertEqual(OnboardingStep.progressIndex(of: .value, signedIn: false), 0)
        XCTAssertEqual(OnboardingStep.progressIndex(of: .tutorial, signedIn: false), 4)
        // The lit dot never runs off the end of the row it is drawn in.
        for step in OnboardingStep.allCases {
            guard let index = OnboardingStep.progressIndex(of: step, signedIn: true) else { continue }
            XCTAssertLessThan(index, OnboardingStep.progressSteps(signedIn: true).count)
        }
    }

    /// A sign-in that succeeds has to leave the sign-in card.
    ///
    /// This is the one step that deletes itself. `OnboardingView.beginSignIn` calls `advance()`
    /// *after* `OmiAuth.signIn` returned, so `advance()` asks for `next(after: .signIn,
    /// signedIn: true)` — and `signedIn: true` is exactly the condition under which
    /// `itinerary(signedIn:)` drops `.signIn`. Looking the current step up in an itinerary it is no
    /// longer on found nothing, nil meant "the flow is over", and `advance()` returned without
    /// moving. The user came back from a completed browser round trip to the card they had just
    /// finished, with no error on it, and pressing the button again only repeated the round trip.
    func testASuccessfulSignInLeavesTheSignInCard() {
        XCTAssertEqual(
            OnboardingStep.next(after: .signIn, signedIn: true), .permissions,
            "signing in must hand the flow to the permissions card, not strand it on sign-in")
    }

    /// The general form of the bug above: no card may dead-end because the itinerary changed while
    /// the user was standing on it. Only `.done` is allowed to have no next step.
    func testNoCardDeadEndsWhenTheItineraryChangesUnderneathIt() {
        for step in OnboardingStep.allCases where step != .done {
            for signedIn in [true, false] {
                XCTAssertNotNil(
                    OnboardingStep.next(after: step, signedIn: signedIn),
                    "\(step) hands the flow nowhere when signedIn: \(signedIn)")
            }
        }
    }
}

// MARK: - Asking one at a time

/// A `PermissionAsking` that records the shape of the run rather than the answers.
///
/// The overlap check is the point: it fails if a second `request` is ever in flight while the first
/// has not returned, which is the exact bug the one-at-a-time pacing exists to prevent — macOS shows
/// one TCC alert at a time, and three fired concurrently stack dialogs the user answers blind.
@MainActor
private final class RecordingAsker: PermissionAsking {
    /// Capabilities that answer "granted" when asked.
    var grants: Set<Capability>
    /// Capabilities already granted before the run starts.
    var alreadyGranted: Set<Capability> = []
    /// Capabilities whose TCC prompt macOS has already spent. A spent prompt is never re-asked; the
    /// pane is the only route left.
    var promptSpent: Set<Capability> = []
    /// A grant made in System Settings, landing on the *n*th poll rather than instantly — which is
    /// what every Screen Recording grant actually looks like.
    var grantsAfterPolls: [Capability: Int] = [:]
    /// True while the grant is real but unusable until a relaunch. Never a reason to keep waiting.
    var screenNeedsRelaunch = false

    private(set) var asked: [Capability] = []
    private(set) var settingsOpened: [Capability] = []
    private(set) var refreshed: [Capability] = []
    private(set) var sawOverlap = false
    private var inFlight = 0

    init(grants: Set<Capability>) {
        self.grants = grants
    }

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
        if inFlight > 0 { sawOverlap = true }
        inFlight += 1
        asked.append(capability)
        // A suspension point inside the ask, so a caller that fired two of these concurrently would
        // genuinely interleave here rather than happening to run to completion in order.
        await Task.yield()
        inFlight -= 1
        promptSpent.insert(capability)
        let granted = grants.contains(capability)
        if granted { alreadyGranted.insert(capability) }
        return granted
    }

    func promptIsSpent(_ capability: Capability) -> Bool { promptSpent.contains(capability) }

    func openSettings(for capability: Capability) { settingsOpened.append(capability) }

    func refresh(_ capability: Capability) async { refreshed.append(capability) }
}

/// The pacing constants are real seconds in production. Every test drives the run at zero, so the
/// suite stays hermetic and instant while the ordering, the non-overlap and the refusal handling —
/// the parts with bugs in them — are exercised exactly as they ship.
@MainActor
private func instantRun(_ asker: PermissionAsking) -> PermissionRun {
    PermissionRun(asking: asker, leadIn: .zero, afterGrant: .zero)
}

/// Lets the gate's task run until it reaches a state, without ever hanging the suite. Bounded by
/// iterations rather than wall-clock, so it stays hermetic on a loaded CI machine.
@MainActor
private func advance(
    until reached: () -> Bool,
    _ message: String,
    file: StaticString = #filePath,
    line: UInt = #line
) async {
    for _ in 0..<2_000 {
        if reached() { return }
        try? await Task.sleep(for: .milliseconds(1))
    }
    XCTFail(message, file: file, line: line)
}

/// The gate at zero pacing, on its own broker so a test never touches the app-wide door.
@MainActor
private func instantGate(
    _ asker: PermissionAsking,
    required: [Capability] = [.microphone, .systemAudio, .screen],
    broker: PermissionBroker? = nil
) -> PermissionGate {
    PermissionGate(
        asking: asker,
        required: required,
        broker: broker ?? PermissionBroker(),
        leadIn: .zero,
        afterGrant: .zero,
        watchPoll: .zero)
}

final class PermissionSequencingTests: XCTestCase {

    /// One at a time, in the fixed order, never two at once.
    @MainActor
    func testPermissionsAreAskedOneAtATimeInTheFixedOrder() async {
        let asker = RecordingAsker(grants: [.microphone, .systemAudio, .screen])
        let landed = await instantRun(asker).run([.microphone, .systemAudio, .screen])

        XCTAssertEqual(asker.asked, [.microphone, .systemAudio, .screen])
        XCTAssertFalse(asker.sawOverlap, "two TCC dialogs were in flight at once")
        XCTAssertEqual(landed, [.microphone, .systemAudio, .screen])
    }

    /// A refusal must not stall the rest of the run.
    ///
    /// `settle` polls for a grant that will never arrive, so the only thing that gets the sequence
    /// past a "no" is the deadline. Without it the run stops on the first decline and the user is
    /// left on a card that never finishes — with two permissions they were never asked for.
    @MainActor
    func testADeclineDoesNotStallTheRestOfTheRun() async {
        let asker = RecordingAsker(grants: [.microphone, .screen])  // system audio says no
        let landed = await instantRun(asker).run([.microphone, .systemAudio, .screen])

        XCTAssertEqual(
            asker.asked, [.microphone, .systemAudio, .screen],
            "the run stopped at the refusal instead of carrying on")
        XCTAssertEqual(landed, [.microphone, .screen])
        XCTAssertFalse(landed.contains(.systemAudio))
    }

    /// Anything already granted is not asked about again. A returning user re-prompted for a
    /// permission they gave last week has been told the app forgot.
    @MainActor
    func testAlreadyGrantedCapabilitiesAreNotAskedAgain() async {
        let asker = RecordingAsker(grants: [.systemAudio, .screen])
        asker.alreadyGranted = [.microphone]
        let landed = await instantRun(asker).run([.microphone, .systemAudio, .screen])

        XCTAssertEqual(asker.asked, [.systemAudio, .screen])
        XCTAssertEqual(landed, [.microphone, .systemAudio, .screen])
    }

    /// The production pacing is what it is because it was tuned once and must not silently drift:
    /// the row is lit alone long enough to read before the dialog covers it, and the new checkmark
    /// is on screen long enough to be witnessed before the next dialog opens over it.
    ///
    /// **The third assertion here is deliberately gone.** It read
    /// `XCTAssertEqual(PermissionRun.settleDeadline, .seconds(2))`, and the constant it guarded no
    /// longer exists — not because 2 s was retuned to some other number, but because *no* number can
    /// be right. Per AGENTS.md a test changed alongside the code it asserts needs an external
    /// citation, and this is it:
    ///
    /// 1. Apple's `CGRequestScreenCaptureAccess()` (CoreGraphics, `CGWindow.h`) "displays a prompt
    ///    to the user" and returns immediately with whether the app *already* has the grant. It does
    ///    not block until the user answers, and the only affirmative button on that alert opens
    ///    System Settings. The answer, if it comes, arrives tens of seconds later in another process.
    /// 2. macOS TCC presents each capability's prompt exactly once per app; after a denial the pane
    ///    is the only remaining route, so "wait a bit longer" can never become "yes".
    /// 3. Measured, not inferred: the live first-run trace at `/tmp/context-for-claude.log` has the
    ///    screen deadline expiring at 10:13:13 and the user opening the Screen Recording pane at
    ///    10:13:46 — 33 seconds later. The app was in the tutorial by 10:14:09 with the grant never
    ///    made and nothing said about it.
    ///
    /// A deadline that decides an answer is therefore replaced by `PermissionGate`'s unbounded
    /// watch, asserted behaviourally in `testAGrantMadeInSettingsIsObservedWithNoDeadline`.
    func testTheDeliberatePacingIsStillInPlace() {
        XCTAssertEqual(PermissionRun.leadIn, .milliseconds(900))
        XCTAssertEqual(PermissionRun.afterGrant, .milliseconds(1_100))
    }
}

// MARK: - The gate: what it takes to leave the card

/// The permissions step used to have two exits and neither consulted a grant. One of them was
/// written under the comment "Move on anyway". These are the assertions that make that unwritable.
final class PermissionGateTests: XCTestCase {

    /// **D1.** No second capability may reach a prompt or a pane while one is in flight.
    ///
    /// Reproduces the live collision exactly: the user is standing in the Screen Recording pane and
    /// a *different* surface asks for a *different* capability 1.9 seconds later. Before the broker
    /// that second call opened the Accessibility pane in the same System Settings window, replacing
    /// the pane the user had been deliberately sent to.
    @MainActor
    func testNoSecondRequestCanStartWhileOneIsInFlight() async {
        let asker = RecordingAsker(grants: [])
        asker.promptSpent = [.microphone]
        let broker = PermissionBroker()
        let gate = instantGate(asker, required: [.microphone], broker: broker)

        let run = Task { await gate.run() }
        await advance(
            until: { gate.phase == .waitingInSettings(.microphone) },
            "the gate never reached the Settings watch")

        // The menu-bar row, the tutorial, the `.done` button — any of the other five entrances.
        let elsewhere = Task { await broker.openSettings(for: .screen) }
        for _ in 0..<50 { try? await Task.sleep(for: .milliseconds(1)) }

        XCTAssertEqual(
            asker.settingsOpened, [.microphone],
            "a second capability opened its pane over the one the user was sent to")
        XCTAssertFalse(asker.sawOverlap)

        gate.postpone(.microphone)
        await run.value
        await elsewhere.value
    }

    /// **The defect, closed at the other end.**
    ///
    /// `SpotlightIsActuallyRequestedTests` asserts the predicate — that `waitingInSettings(.screen)`
    /// names screen recording. That is only half a guard: a predicate that is right about a phase
    /// nothing ever reaches is the same as no predicate at all. So this drives the **real gate**
    /// through the **real screen-recording episode** and asserts it genuinely lands in a phase the
    /// predicate names, with the pane really opened.
    ///
    /// Which is exactly the shape of what shipped. `waitingInSettings(.screen)` was reached on every
    /// single run, the pane was opened every time, the card said so — and nothing asked for an
    /// overlay, because no call site existed to ask.
    @MainActor
    func testTheScreenRecordingEpisodeReachesAPhaseThatAsksForTheSpotlight() async {
        let asker = RecordingAsker(grants: [])
        // macOS has spent the prompt, which is the ordinary state for Screen Recording: it is the one
        // grant that can only be given in System Settings.
        asker.promptSpent = [.screen]
        let gate = instantGate(asker, required: [.screen])

        let run = Task { await gate.run() }
        await advance(
            until: { gate.phase == .waitingInSettings(.screen) },
            "the gate never reached the Settings watch for screen recording")

        XCTAssertEqual(
            PermissionGate.spotlightSubject(of: gate.phase), .screen,
            "the gate is standing in the Screen Recording pane for the user and nothing is being "
                + "asked to point at the row — this is the defect, exactly as it shipped")
        XCTAssertEqual(asker.settingsOpened, [.screen], "and the pane really was opened")

        gate.postpone(.screen)
        await run.value
    }

    /// **D2, the headline bug.** Nothing granted, nothing answered — the card may not be left.
    @MainActor
    func testTheStepDoesNotCompleteWhileAnyRequiredCapabilityIsUnanswered() async {
        let asker = RecordingAsker(grants: [])
        let gate = instantGate(asker, required: [.microphone])

        let run = Task { await gate.run() }
        await advance(
            until: { gate.phase == .waitingInSettings(.microphone) },
            "the gate never reached the Settings watch")

        XCTAssertFalse(gate.canLeaveStep, "the step completed with a refused permission and no answer")
        XCTAssertNil(gate.answers[.microphone])

        run.cancel()
        await run.value
    }

    /// **The anti-dead-end.** The only thing other than a grant that completes the step is a button
    /// the user pressed on purpose — never a default, never a timeout.
    @MainActor
    func testAnExplicitDeferralIsWhatCompletesTheStep() async {
        let asker = RecordingAsker(grants: [])
        let gate = instantGate(asker)

        let run = Task { await gate.run() }
        for capability in [Capability.microphone, .systemAudio, .screen] {
            await advance(
                until: { gate.phase == .waitingInSettings(capability) },
                "the gate never reached the Settings watch for \(capability)")
            XCTAssertFalse(gate.canLeaveStep, "\(capability) was still unanswered")
            gate.postpone(capability)
        }
        await run.value

        XCTAssertTrue(gate.canLeaveStep)
        XCTAssertEqual(gate.phase, .complete)
        XCTAssertEqual(gate.answers[.screen], .deferred)
    }

    /// **D3.** A grant made in System Settings arrives long after any deadline would have expired.
    /// This is the assertion that replaces `settleDeadline == 2s`.
    @MainActor
    func testAGrantMadeInSettingsIsObservedWithNoDeadline() async {
        let asker = RecordingAsker(grants: [])
        asker.promptSpent = [.screen]
        asker.grantsAfterPolls = [.screen: 20]
        let gate = instantGate(asker, required: [.screen])

        await gate.run()

        XCTAssertEqual(gate.answers[.screen], .granted, "the watch gave up on a grant that did arrive")
        XCTAssertTrue(gate.canLeaveStep)
        XCTAssertTrue(asker.refreshed.contains(.screen), "the watch has to re-ask, not just re-read")
    }

    /// **The deadlock the fix must not introduce.** Screen Recording takes effect only in a new
    /// process, so `screenNeedsRelaunch` stays true until the app is reopened. Gating on it would
    /// mean the card could never be left. `CGPreflightScreenCaptureAccess()` — `isGranted` — flips
    /// in *this* process at the moment of the grant, and that is what the gate reads.
    @MainActor
    func testScreenRecordingCompletesWithoutWaitingForARelaunch() async {
        let asker = RecordingAsker(grants: [])
        asker.alreadyGranted = [.microphone, .systemAudio]
        asker.promptSpent = [.screen]
        // The real shape: the switch is flipped in System Settings some polls later, and the grant
        // is immediately readable in this process while capture stays dead until a relaunch.
        asker.grantsAfterPolls = [.screen: 5]
        asker.screenNeedsRelaunch = true
        let gate = instantGate(asker)

        await gate.run()

        XCTAssertEqual(gate.answers[.screen], .granted)
        XCTAssertTrue(gate.canLeaveStep, "a grant waiting on a relaunch is still the user's answer")
        XCTAssertEqual(gate.phase, .complete)
    }

    /// **The re-prompt trap.** macOS shows each prompt exactly once; asking again does nothing at
    /// all and the row looks dead. A spent prompt goes straight to the pane, once.
    @MainActor
    func testAnExhaustedPromptOpensSettingsInsteadOfReAsking() async {
        let asker = RecordingAsker(grants: [])
        asker.promptSpent = [.microphone]
        let gate = instantGate(asker, required: [.microphone])

        let run = Task { await gate.run() }
        await advance(
            until: { gate.phase == .waitingInSettings(.microphone) },
            "the gate never reached the Settings watch")

        XCTAssertFalse(asker.asked.contains(.microphone), "a spent prompt was asked a second time")
        XCTAssertEqual(asker.settingsOpened, [.microphone], "one ask, one pane")

        gate.postpone(.microphone)
        await run.value
        XCTAssertEqual(asker.settingsOpened, [.microphone], "the pane was opened again on the way out")
    }

    /// **D4.** The card is ordered out only while something else genuinely owns the screen. Hiding
    /// on `explaining` is what spent the entire 900 ms lead-in — and the preamble the card exists to
    /// show — behind an ordered-out window, and made the card blink out three times per run.
    ///
    /// `waitingInSettings` is conditional on purpose: this app is `LSUIElement`, so a card ordered
    /// out has no Dock icon to bring it back, and a card hidden on a phase alone is a card whose
    /// "I'll do this later" button can never be pressed.
    func testTheCardIsOnlyHiddenWhileSomethingElseOwnsTheScreen() {
        for frontmost in [true, false] {
            XCTAssertFalse(PermissionGate.cardYields(to: .idle, settingsIsFrontmost: frontmost))
            XCTAssertFalse(
                PermissionGate.cardYields(to: .explaining(.microphone), settingsIsFrontmost: frontmost),
                "the lead-in is the card being read; hiding through it is the bug")
            XCTAssertFalse(
                PermissionGate.cardYields(to: .confirming(.microphone), settingsIsFrontmost: frontmost),
                "a confirmation nobody can witness is the same as no confirmation")
            XCTAssertTrue(
                PermissionGate.cardYields(to: .prompting(.microphone), settingsIsFrontmost: frontmost),
                "a system dialog is up and the card is in the way")
            XCTAssertFalse(PermissionGate.cardYields(to: .complete, settingsIsFrontmost: frontmost))
        }

        XCTAssertTrue(
            PermissionGate.cardYields(to: .waitingInSettings(.screen), settingsIsFrontmost: true))
        XCTAssertFalse(
            PermissionGate.cardYields(to: .waitingInSettings(.screen), settingsIsFrontmost: false),
            "back in front of the card, the escape has to be reachable")
    }

    /// Already-granted capabilities are answered without an ask and without a pane. A returning user
    /// re-prompted for a permission they gave last week has been told the app forgot.
    @MainActor
    func testAnAlreadyGrantedRunCompletesWithoutAskingOrOpeningAnything() async {
        let asker = RecordingAsker(grants: [])
        asker.alreadyGranted = [.microphone, .systemAudio, .screen]
        let gate = instantGate(asker)

        await gate.run()

        XCTAssertEqual(asker.asked, [])
        XCTAssertEqual(asker.settingsOpened, [])
        XCTAssertTrue(gate.canLeaveStep)
    }
}

// MARK: - Grouping

final class CapabilityGroupTests: XCTestCase {

    /// A group reads "Granted" only when **every** member is.
    ///
    /// This is the one thing the menu bar row cannot get wrong. "Microphone" stands for the mic *and*
    /// the system-audio tap; "Screen" for the pixels *and* the window text. A row that says granted
    /// over a half-missing capability is the row lying about what the app can do.
    func testAGroupIsGrantedOnlyWhenEveryMemberIs() {
        XCTAssertEqual(CapabilityGroup.microphone.members, [.microphone, .systemAudio])
        XCTAssertEqual(CapabilityGroup.screen.members, [.screen, .accessibility])

        for group in CapabilityGroup.allCases {
            XCTAssertTrue(group.isGranted { group.members.contains($0) }, "\(group) with all members in")
            for missing in group.members {
                XCTAssertFalse(
                    group.isGranted { $0 != missing },
                    "\(group) read as granted while \(missing) was missing")
            }
        }
    }

    /// The status word comes from the first member still waiting, so the row describes the work that
    /// remains rather than the best case.
    func testTheGroupReportsTheNearestMissingMemberFirst() {
        XCTAssertEqual(CapabilityGroup.screen.firstMissing { $0 != .accessibility }, .accessibility)
        XCTAssertEqual(CapabilityGroup.screen.firstMissing { _ in false }, .screen)
        XCTAssertNil(CapabilityGroup.microphone.firstMissing { _ in true })
    }

    /// The same rule through the report the menu bar actually renders.
    func testTheGroupedReportCarriesTheRuleThroughToTheMenuBar() {
        let halfMissing = Permissions.groupedReport { $0 == .microphone }
        let microphone = halfMissing.first { $0.name == CapabilityGroup.microphone.rawValue }
        XCTAssertEqual(microphone?.granted, false, "the mic alone must not read as the group granted")

        let all = Permissions.groupedReport { _ in true }
        XCTAssertEqual(all.count, CapabilityGroup.allCases.count)
        XCTAssertTrue(all.allSatisfy(\.granted))
    }
}

// MARK: - Locating the real row

/// A stand-in accessibility tree, so the locator runs with no System Settings, no grant, and no
/// window server.
/// Internal rather than file-private: `SettingsSpotlightTests` builds scenes out of these panes, and
/// a second copy of the tree shapes measured off a real macOS is exactly the kind of duplicate that
/// drifts from the thing it was copied from.
struct FakeElement: SettingsElement {
    var elementRole: String?
    var elementIdentifier: String?
    var elementValue: String?
    var elementFrame: CGRect?
    var elementDescription: String?
    var children: [FakeElement] = []

    var elementChildren: [any SettingsElement] { children }
}

/// The pane shapes measured on macOS 26.5.2 (build 25F84), reproduced from the real trees dumped
/// off this machine — different structures, one pair of identifiers.
enum PaneFixture {
    static let appName = "Context for Claude"

    static func title(_ name: String, y: CGFloat) -> FakeElement {
        FakeElement(
            elementRole: kAXStaticTextRole,
            elementIdentifier: "\(name)_Title",
            elementValue: name,
            elementFrame: CGRect(x: 611, y: y, width: 146, height: 24))
    }

    static func toggle(_ name: String, y: CGFloat, on: Bool) -> FakeElement {
        FakeElement(
            elementRole: kAXCheckBoxRole,
            elementIdentifier: "\(name)_Toggle",
            elementValue: on ? "1" : "0",
            elementFrame: CGRect(x: 1017, y: y + 6, width: 36, height: 16))
    }

    /// Microphone: flat. Label and switch are sibling leaves of one group.
    static func flatPane(apps: [String], on: Bool = false, scrollHeight: CGFloat = 800) -> FakeElement {
        var leaves: [FakeElement] = []
        for (index, app) in apps.enumerated() {
            let y = 132 + CGFloat(index) * 43
            leaves.append(title(app, y: y))
            leaves.append(toggle(app, y: y, on: on))
        }
        return FakeElement(
            elementRole: kAXWindowRole,
            elementFrame: CGRect(x: 360, y: 34, width: 723, height: 948),
            children: [
                FakeElement(
                    elementRole: kAXScrollAreaRole,
                    elementFrame: CGRect(x: 583, y: 86, width: 500, height: scrollHeight),
                    children: [
                        FakeElement(
                            elementRole: kAXGroupRole,
                            elementFrame: CGRect(x: 603, y: 86, width: 460, height: 1068),
                            children: leaves)
                    ])
            ])
    }

    /// Screen Recording and Accessibility: an outline of `AXRow` → `AXCell` → leaves. `sections` is
    /// what makes the Screen Recording pane's two lists — an app appears in both.
    static func outlinePane(sections: [[String]], on: Bool = false) -> FakeElement {
        var groups: [FakeElement] = []
        var y: CGFloat = 145
        for apps in sections {
            var rows: [FakeElement] = []
            for app in apps {
                rows.append(
                    FakeElement(
                        elementRole: kAXRowRole,
                        elementFrame: CGRect(x: 603, y: y, width: 460, height: 40),
                        children: [
                            FakeElement(
                                elementRole: kAXCellRole,
                                elementFrame: CGRect(x: 603, y: y, width: 460, height: 40),
                                children: [title(app, y: y + 8), toggle(app, y: y + 8, on: on)])
                        ]))
                y += 40
            }
            groups.append(
                FakeElement(
                    elementRole: kAXScrollAreaRole,
                    elementFrame: CGRect(x: 603, y: 145, width: 460, height: 1_600),
                    children: [
                        FakeElement(
                            elementRole: kAXOutlineRole,
                            elementFrame: CGRect(x: 603, y: 145, width: 460, height: 1_600),
                            children: rows)
                    ]))
            y += 60
        }
        return FakeElement(
            elementRole: kAXWindowRole,
            elementFrame: CGRect(x: 360, y: 34, width: 723, height: 2_000),
            children: [
                FakeElement(
                    elementRole: kAXScrollAreaRole,
                    elementFrame: CGRect(x: 583, y: 86, width: 500, height: 1_900),
                    children: groups)
            ])
    }

    /// **The Screen Recording pane as a first run actually meets it**: other applications listed, and
    /// ours sitting *below* the list as a loose row that has to be dragged up into it.
    ///
    /// This is macOS 26's own affordance and it is the shape the whole two-region overlay exists for.
    /// The stray row is a sibling of the section rather than a child of it, which is precisely what
    /// makes `SettingsRowLocator` report `notListed` with a `strayRow` instead of a hit — the walk
    /// only records a stray label when it is outside every section.
    /// The window the *window server* reports for this pane, which is the only authority on the
    /// window and is deliberately shorter than the scroll content the accessibility tree describes.
    static let dragPaneWindow = CGRect(x: 360, y: 34, width: 723, height: 948)
    /// The list rows live in — the drop target.
    static let dragPaneList = CGRect(x: 603, y: 145, width: 460, height: 300)
    /// Our row, loose below the list.
    static let dragPaneStrayRow = CGRect(x: 611, y: 520, width: 420, height: 32)

    static func dragPane(listed: [String] = ["Claude", "Cursor", "Granola"]) -> FakeElement {
        var rows: [FakeElement] = []
        var y = dragPaneList.minY
        for app in listed {
            rows.append(
                FakeElement(
                    elementRole: kAXRowRole,
                    elementFrame: CGRect(x: dragPaneList.minX, y: y, width: dragPaneList.width, height: 40),
                    children: [
                        FakeElement(
                            elementRole: kAXCellRole,
                            elementFrame: CGRect(
                                x: dragPaneList.minX, y: y, width: dragPaneList.width, height: 40),
                            children: [title(app, y: y + 8), toggle(app, y: y + 8, on: true)])
                    ]))
            y += 40
        }
        return FakeElement(
            elementRole: kAXWindowRole,
            elementFrame: dragPaneWindow,
            children: [
                FakeElement(
                    elementRole: kAXScrollAreaRole,
                    elementFrame: CGRect(x: 583, y: 86, width: 500, height: 860),
                    children: [
                        FakeElement(
                            elementRole: kAXOutlineRole, elementFrame: dragPaneList, children: rows),
                        // The loose row: a label of ours, outside every section. That is exactly what
                        // makes the locator answer `notListed` with a `strayRow` rather than a hit.
                        FakeElement(
                            elementRole: kAXStaticTextRole,
                            elementIdentifier: "\(appName)_Title",
                            elementValue: appName,
                            elementFrame: dragPaneStrayRow),
                    ])
            ])
    }
}

final class SettingsRowLocatorTests: XCTestCase {
    private let locator = SettingsRowLocator(appName: PaneFixture.appName)

    /// The flat pane. The ring is the label through the switch — not the switch alone, which on a
    /// 460 pt row reads as a dot beside the thing instead of around it.
    func testFindsTheRowInTheFlatMicrophonePane() {
        let pane = PaneFixture.flatPane(apps: ["Arc", "Claude", PaneFixture.appName, "Cursor"])
        guard case .visible(let located) = locator.locate(in: pane) else {
            return XCTFail("the row was not located in the flat pane")
        }
        XCTAssertEqual(located.toggle.minX, 1017)
        XCTAssertEqual(located.row.minX, 611, "the ring starts at the label, not at the switch")
        XCTAssertEqual(located.row.maxX, 1053)
        XCTAssertFalse(located.isOn)
    }

    /// The outline pane, with its extra two levels of wrapping.
    func testFindsTheRowInTheOutlinePane() {
        let pane = PaneFixture.outlinePane(sections: [["Claude", PaneFixture.appName, "Cursor"]], on: true)
        guard case .visible(let located) = locator.locate(in: pane) else {
            return XCTFail("the row was not located in the outline pane")
        }
        XCTAssertTrue(located.isOn, "the switch's own state has to come off the switch")
        XCTAssertTrue(located.row.contains(located.toggle.center))
    }

    /// The Screen Recording pane on macOS 26 lists an app **twice** — once under "Screen & System
    /// Audio Recording" and again under "System Audio Recording Only". Ringing the wrong one is the
    /// mispositioned overlay arriving by a plausible route, so the section is chosen explicitly.
    func testDisambiguatesTheTwoSectionsOfTheScreenRecordingPane() {
        let pane = PaneFixture.outlinePane(sections: [
            ["Claude", PaneFixture.appName, "Cursor"],
            [PaneFixture.appName, "Granola"],
        ])
        guard case .visible(let screen) = locator.locate(in: pane, preferring: 0),
            case .visible(let audio) = locator.locate(in: pane, preferring: 1)
        else { return XCTFail("both sections should hold a row") }

        XCTAssertNotEqual(screen.row, audio.row)
        XCTAssertLessThan(screen.row.minY, audio.row.minY, "section 0 is the upper list")
    }

    /// Every capability picks a section explicitly, and every one picks the first.
    ///
    /// The value matters less than the fact that it is stated: the pane each capability opens has one
    /// list that is the right one, and "whichever row the walk reached first" would be correct only by
    /// luck. Measured live: a probe run against the Accessibility pane produced 477 locations, all at
    /// the identical rect, and 112 refusals — every refusal while a different pane was on screen.
    /// **System audio picks the second list**, and this asserted 0 for all four while
    /// `Capability.systemAudio.settingsPane` opened the *Microphone* pane — a pair that was
    /// self-consistent and wrong together. Source for the new value, captured live on macOS 26.5.2
    /// (25F84) rather than read off the code it checks: Privacy & Security ▸ Screen & System Audio
    /// Recording renders *two* lists — "Screen & System Audio Recording", then "System Audio
    /// Recording Only" — and this app appears in **both**. The Microphone pane lists the CoreAudio
    /// tap nowhere at all.
    func testEveryCapabilityChoosesItsSectionExplicitly() {
        for capability in Capability.allCases where capability != .systemAudio {
            XCTAssertEqual(
                PermissionChoreography.sectionOccurrence(for: capability), 0,
                "\(capability) opens a pane whose first list is the right one")
        }

        XCTAssertEqual(
            PermissionChoreography.sectionOccurrence(for: .systemAudio), 1,
            "the tap's switch is in “System Audio Recording Only”, the second list")
    }

    /// The two halves of that pair have to name the same pane, or the overlay rings a real row on the
    /// wrong screen with total confidence — worse than not pointing at all.
    func testSystemAudioPointsAtTheSamePaneItOpens() {
        XCTAssertEqual(
            Capability.systemAudio.settingsPane, Capability.screen.settingsPane,
            "both switches live in Privacy & Security ▸ Screen & System Audio Recording")
        XCTAssertNotEqual(
            Capability.systemAudio.settingsPane, Capability.microphone.settingsPane,
            "the Microphone pane does not list the CoreAudio tap at all")
        XCTAssertNotEqual(
            PermissionChoreography.sectionOccurrence(for: .systemAudio),
            PermissionChoreography.sectionOccurrence(for: .screen),
            "same pane, different lists — telling them apart is the whole job")
    }

    /// An app that is not in the list is not somebody else's row.
    func testDoesNotMistakeAnotherApplicationsRowForOurs() {
        let pane = PaneFixture.flatPane(apps: ["Arc", "Claude", "Cursor"])
        XCTAssertEqual(locator.locate(in: pane), .notFound)
    }

    /// A row scrolled out of its list still answers with a perfectly plausible frame — one that is
    /// nowhere the user can see. Reporting it as visible is exactly how a ring ends up drawn over
    /// empty screen, so the clip stack is checked against every ancestor scroll area.
    func testARowScrolledOutOfTheListIsReportedAsOffscreenRatherThanPointedAt() {
        let pane = PaneFixture.flatPane(
            apps: ["Arc", "Claude", "Comet", "Discord", "Figma", PaneFixture.appName],
            scrollHeight: 120)
        guard case .offscreen = locator.locate(in: pane) else {
            return XCTFail("a clipped row must not be reported as visible")
        }
    }

    /// The bounds are not decoration. An application can claim any number of children and nest
    /// without end, and this walk runs while the user is waiting on it.
    func testTheWalkIsBounded() {
        var deep = FakeElement(
            elementRole: kAXGroupRole, elementFrame: .zero,
            children: [
                PaneFixture.title(PaneFixture.appName, y: 0),
                PaneFixture.toggle(PaneFixture.appName, y: 0, on: true),
            ])
        for _ in 0..<80 {
            deep = FakeElement(elementRole: kAXGroupRole, elementFrame: .zero, children: [deep])
        }
        let window = FakeElement(
            elementRole: kAXWindowRole,
            elementFrame: CGRect(x: 0, y: 0, width: 1_000, height: 1_000),
            children: [deep])
        // Nested past `maxDepth`, so it is never reached — and the walk returns rather than
        // recursing until the stack gives out.
        XCTAssertEqual(locator.locate(in: window), .notFound)
    }
}

// MARK: - Degrading honestly

final class PermissionGuidanceTests: XCTestCase {

    /// The whole contract of this file in one assertion: **a failed lookup produces a sentence, never
    /// a ring.** A confident arrow aimed at empty screen is worse than text, because the user follows
    /// it and finds nothing there.
    func testAFailedLookupDegradesToAPlainInstructionAndNeverPoints() {
        // Nothing found at all — which is what happens when Accessibility itself is not yet granted
        // and `LiveSettingsElement.systemSettingsWindows()` comes back empty.
        let nothing = PermissionChoreography.guidance(
            for: .accessibility, appName: PaneFixture.appName, windows: [])
        XCTAssertFalse(nothing.isPointing)
        guard case .instruction(let sentence) = nothing else { return XCTFail("expected an instruction") }
        XCTAssertTrue(sentence.contains("Accessibility"), "the sentence has to name the pane: \(sentence)")
        XCTAssertTrue(sentence.contains(PaneFixture.appName), "and the row: \(sentence)")

        // Found, but scrolled out of view. Still a sentence — a different one, because "scroll down"
        // is something the user can act on and "open the pane" is not.
        let clipped = PermissionChoreography.guidance(
            for: .microphone,
            appName: PaneFixture.appName,
            windows: [
                PaneFixture.flatPane(
                    apps: ["Arc", "Claude", "Comet", "Discord", "Figma", PaneFixture.appName],
                    scrollHeight: 120)
            ])
        XCTAssertFalse(clipped.isPointing)
        guard case .instruction(let scrolledSentence) = clipped else { return XCTFail("expected an instruction") }
        XCTAssertTrue(
            scrolledSentence.lowercased().contains("scroll"),
            "a row that exists but is out of view should say so: \(scrolledSentence)")
        XCTAssertNotEqual(sentence, scrolledSentence)
    }

    /// And the positive case, so the test above is not passing because nothing ever points.
    func testAVisibleRowIsPointedAt() {
        let guidance = PermissionChoreography.guidance(
            for: .microphone,
            appName: PaneFixture.appName,
            windows: [PaneFixture.flatPane(apps: ["Arc", PaneFixture.appName])])
        guard case .pointing(let located) = guidance else {
            return XCTFail("a visible row must be pointed at, or the overlay is never useful")
        }
        XCTAssertGreaterThan(located.row.width, located.toggle.width)
        XCTAssertTrue(guidance.isPointing)
    }

    /// A pane whose layout we have never seen: the identifiers gone, the labels still there. The
    /// label's text is the fallback, and it is what keeps the overlay working on a macOS that
    /// renamed the identifier rather than degrading everyone to a sentence.
    func testFallsBackToTheLabelTextWhenTheIdentifiersAreGone() {
        var pane = PaneFixture.flatPane(apps: [PaneFixture.appName])
        pane.children[0].children[0].children = pane.children[0].children[0].children.map { leaf in
            var leaf = leaf
            leaf.elementIdentifier = nil
            return leaf
        }
        guard case .pointing = PermissionChoreography.guidance(
            for: .microphone, appName: PaneFixture.appName, windows: [pane])
        else { return XCTFail("the label's own text should still find the row") }
    }

    /// **The Accessibility bootstrap says *why* it is degraded, not merely that it is.**
    ///
    /// The step that asks for Accessibility cannot read the row that grants it. Measured on macOS
    /// 26.5.2 (25F84) from a process with `AXIsProcessTrusted() == false`, every read of System
    /// Settings' tree comes back `kAXErrorAPIDisabled`: the windows, the role, the title, the
    /// attribute *name* list, hit testing through `AXUIElementCopyElementAtPosition`, and the same
    /// read asked through System Events. There is no narrower question that is allowed, which is why
    /// this tier exists at all.
    ///
    /// So it carries the cause. `awaitingTrust` is not a label: it is what tells the tracker this
    /// answer costs 0.55 ms to re-take rather than a 727 ms tree walk, and that the one event it is
    /// waiting for is the user flipping the very switch the overlay was opened to talk about.
    /// Reported as `unreadable`, the overlay would keep showing a degraded boundary for up to 800 ms
    /// after the grant had already landed.
    func testTheUntrustedBootstrapReportsThatItIsWaitingForTheGrant() {
        let space = ScreenSpace(displays: [
            DisplayGeometry(appKitFrame: CGRect(x: 0, y: 0, width: 1_512, height: 982))
        ])
        let window = CGRect(x: 0, y: 33, width: 723, height: 948)

        let bootstrap = PermissionChoreography.framingOrWords(
            for: .accessibility, frame: window, space: space, trusted: false, windows: 0)
        guard case .framing(let framed) = bootstrap else {
            return XCTFail("a window on screen is still worth lighting out of the desktop")
        }
        XCTAssertEqual(framed.window, window)
        XCTAssertEqual(framed.cause, .awaitingTrust)

        // And the expensive case is not mislabelled as the cheap one. Trusted, the tree walked, the
        // row still not found: re-asking costs the whole walk, and nothing the user is about to do
        // changes that.
        let walked = PermissionChoreography.framingOrWords(
            for: .accessibility, frame: window, space: space, trusted: true, windows: 1)
        guard case .framing(let unreadable) = walked else { return XCTFail("expected a framing") }
        XCTAssertEqual(unreadable.cause, .unreadable)

        // No window at all is still words alone — knowing *why* we cannot read the pane has not
        // become a licence to draw around something nobody measured.
        guard case .instruction = PermissionChoreography.framingOrWords(
            for: .accessibility, frame: nil, space: space, trusted: false, windows: 0)
        else { return XCTFail("nothing measured means nothing drawn") }
    }

    /// Every capability has a sentence, and every sentence names a place. A capability that fell
    /// through to a generic "check System Settings" would be the degraded path degrading further.
    func testEveryCapabilityHasAnInstructionThatNamesItsPane() {
        for capability in Capability.allCases {
            let sentence = PermissionChoreography.instruction(
                for: capability, appName: PaneFixture.appName, scrolled: false)
            XCTAssertTrue(sentence.contains("Privacy & Security"), "\(capability): \(sentence)")
            XCTAssertTrue(sentence.contains(PaneFixture.appName), "\(capability): \(sentence)")
        }
    }
}

extension CGRect {
    fileprivate var center: CGPoint { CGPoint(x: midX, y: midY) }
}

// MARK: - No timer acts for the user

/// **A static checker, not behavioural coverage.** It reads `OnboardingView.swift` as text. It cannot
/// prove the card behaves; it can only prove the scheduling primitives that used to make it behave
/// badly are gone, and say exactly which line brought one back.
///
/// It exists because the defect it guards is invisible to every seam this suite has. The card
/// dismissed itself 1.6 s after the last step arrived, relaunched the app 1.5 s after a grant landed,
/// and drew every button at `opacity(0)` until a 340 ms timer fired — none of which any assertion on
/// `OnboardingStep` or `PermissionInvitations` can see, because none of it goes through them. The
/// rule they violated was given as: *"During onboarding have no time based triggers. Only after
/// clicks or user pressing continue or grant permission."*
///
/// The honest test would drive a real `OnboardingView` and assert that no window closes while nothing
/// is pressed. SwiftUI gives no seam to do that, and inventing one would mean the view under test is
/// not the view that ships. So: a tripwire, labelled as one. If `OnboardingView` ever gains a
/// protocol-shaped clock, delete this and assert the behaviour instead.
final class OnboardingHasNoTimedTriggersTests: XCTestCase {

    /// The one timed thing the flow keeps, and why it is allowed.
    ///
    /// macOS posts no notification for a TCC grant or for System Settings coming forward, so polling
    /// is the only way to *detect* an action the user has already taken. Detection is not a trigger:
    /// what these polls do when they succeed is offer a button.
    private let permittedPolls = [
        "Permissions.grantWatchPoll",  // watching for a switch the user flips in System Settings
        "waitForSettingsFrontmost",  // waiting for the pane to exist before pointing at it
    ]

    /// Anything that can run code later, which is the whole family the rule is about.
    private let schedulingPrimitives = [
        "Task.sleep",
        "asyncAfter",
        "Timer.publish",
        "scheduledTimer",
    ]

    func testNothingInTheOnboardingCardIsScheduledOnAClock() throws {
        let source = try onboardingSource()

        var offenders: [(line: Int, text: String)] = []
        for (index, raw) in source.components(separatedBy: "\n").enumerated() {
            let line = raw.trimmingCharacters(in: .whitespaces)
            guard schedulingPrimitives.contains(where: line.contains) else { continue }
            guard !permittedPolls.contains(where: line.contains) else { continue }
            offenders.append((index + 1, line))
        }

        XCTAssertTrue(
            offenders.isEmpty,
            """
            OnboardingView schedules work on a clock:
            \(offenders.map { "  OnboardingView.swift:\($0.line): \($0.text)" }.joined(separator: "\n"))

            Onboarding advances only on a click, Continue, or a grant. If this line watches for \
            something the user did, route it through Permissions.grantWatchPoll or \
            waitForSettingsFrontmost — both are on the allow-list above, and both may only ever \
            end by offering a control, never by pressing one.
            """)
    }

    /// The two specific things that used to happen without the user, named so a regression reads as
    /// the bug rather than as an anonymous style violation.
    func testTheCardNeitherClosesNorRestartsItself() throws {
        let source = try onboardingSource()

        for (action, needle) in [
            ("close the window", "OnboardingWindow.dismiss()"),
            ("restart the app", "Permissions.relaunchApp()"),
        ] {
            let callers = functionsCalling(needle, in: source)
            XCTAssertFalse(callers.isEmpty, "expected \(needle) to still be called somewhere")
            for caller in callers {
                XCTAssertTrue(
                    caller.hasPrefix("close") || caller.hasPrefix("restart"),
                    """
                    \(needle) is reached from \(caller)(), which is not a button handler — the flow \
                    must never \(action) on its own. closeOnboarding() and restartForScreenGrant() \
                    are the only paths, and both are pressed.
                    """)
            }
        }
    }

    // MARK: Helpers

    private func onboardingSource() throws -> String {
        let url = InkSourceSweep.uiSourceRoot.appendingPathComponent("Onboarding/OnboardingView.swift")
        return InkSourceSweep.strippingComments(from: try String(contentsOf: url, encoding: .utf8))
    }

    /// The `private func` / `private var` each occurrence of `needle` sits inside.
    ///
    /// Brace-free and deliberately crude: it walks declarations in order and attributes a hit to the
    /// most recent one. That is sound here because `OnboardingView` declares its members flat.
    private func functionsCalling(_ needle: String, in source: String) -> [String] {
        var current = "<file scope>"
        var found: [String] = []
        for raw in source.components(separatedBy: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if let name = declarationName(of: line) { current = name }
            if line.contains(needle) { found.append(current) }
        }
        return found
    }

    private func declarationName(of line: String) -> String? {
        for keyword in ["private func ", "func ", "private var ", "var "] {
            guard line.hasPrefix(keyword) else { continue }
            let rest = line.dropFirst(keyword.count)
            let name = rest.prefix { $0.isLetter || $0.isNumber || $0 == "_" }
            return name.isEmpty ? nil : String(name)
        }
        return nil
    }
}
