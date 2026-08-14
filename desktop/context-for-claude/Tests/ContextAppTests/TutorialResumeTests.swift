import AppKit
import ContextCore
import XCTest

@testable import ContextApp

/// **A process death in the middle of the walkthrough is a designed-for event, not a crash.**
///
/// `TutorialStep.screenAccess` asks for Screen Recording, and macOS answers with a dialog offering
/// **"Quit & Reopen"** — because a screen grant only reaches a process that already held it when it
/// connected to the window server. So the flow's own second beat can end the process, and everything
/// here is about the process that comes back.
///
/// What it used to come back to was the Activity panel with the walkthrough gone: `context.onboarded`
/// is already true and `OnboardingResume` already spent by the time the tutorial starts, and nothing
/// in the menu bar or Settings can start one. This is the memory that was missing, the ordering that
/// consults it, and the two states the memory must *not* survive.
@MainActor
final class TutorialResumeTests: XCTestCase {

    // MARK: - Harness

    /// A scratch defaults domain per test. The machine running the tests is the machine the app runs
    /// on, so touching `UserDefaults.standard` here would rewrite the developer's own walkthrough
    /// state — the same reason `OnboardingResumeTests` builds its own suite.
    private func scratch() throws -> (UserDefaults, () -> Void) {
        let suite = "com.omi.context-for-claude.TutorialResumeTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        return (defaults, { UserDefaults.standard.removePersistentDomain(forName: suite) })
    }

    /// Answers the world however a test likes, and records every resume-point write and clear.
    ///
    /// Deliberately its own world rather than a share of `TutorialTests`': what these tests need to
    /// see is the two calls nothing else in the flow makes, and a world that also had to satisfy the
    /// render harness would hide them among thirty counters.
    @MainActor
    private final class World {
        var clock: Double = 1_700_000_000
        var screenGranted = false
        var frameCount = 0
        var stampURL: URL?
        var timelineIsVisible = false
        var searchPanelIsVisible = false

        /// Every beat written to the resume point, in order, and every time it was spent.
        var recorded: [TutorialStep] = []
        var clears = 0
        /// How many times the run asked the system what it can see. A resumed run has to ask; a
        /// resumed run that trusted the beat it woke on would not.
        var screenReads = 0

        var overlayPresented: [TutorialStep] = []
        var overlayDismissals = 0
        var spotlightHides = 0
        var pagesOpened: [URL] = []

        var hotkeyWatch: (() -> Void)?
        var dragWatch: (() -> Void)?
        var searchPanelWatch: ((SearchPanelEvent) -> Void)?

        func environment() -> TutorialEnvironment {
            var environment = TutorialEnvironment()
            environment.pollInterval = nil
            environment.now = { self.clock }
            environment.frameCount = { _ in self.frameCount }
            environment.screenIsGranted = {
                self.screenReads += 1
                return self.screenGranted
            }
            environment.openPage = { url in
                self.pagesOpened.append(url)
                return true
            }
            environment.askClaude = { _, _, answer in
                answer(.prompted(restarted: false, mayNotReachMe: false))
            }
            environment.activityChord = { "⌘ + ⌘" }
            environment.activityChordIsArmed = { true }
            environment.watchForActivityHotkey = { self.hotkeyWatch = $0 }
            environment.stopWatchingActivityHotkey = { self.hotkeyWatch = nil }
            environment.watchForDrag = { self.dragWatch = $0 }
            environment.stopWatchingDrag = { self.dragWatch = nil }
            environment.presentTimeline = { self.timelineIsVisible = true }
            environment.dismissTimeline = { self.timelineIsVisible = false }
            environment.timelineIsVisible = { self.timelineIsVisible }
            environment.watchSearchPanel = { self.searchPanelWatch = $0 }
            environment.stopWatchingSearchPanel = { self.searchPanelWatch = nil }
            environment.searchPanelIsVisible = { self.searchPanelIsVisible }
            environment.presentSearchPanel = { self.report(.opened) }
            environment.dismissSearchPanel = { self.report(.closed) }
            environment.presentOverlay = { self.overlayPresented.append($0) }
            environment.dismissOverlay = { self.overlayDismissals += 1 }
            environment.hideMenuBarSpotlight = { self.spotlightHides += 1 }
            environment.recordResumePoint = { self.recorded.append($0) }
            environment.clearResumePoint = { self.clears += 1 }
            environment.newToolCall = { since in
                guard let url = self.stampURL else { return nil }
                return QueryStamp.newCall(since: since, from: url)
            }
            return environment
        }

        /// The real panel says what it just did, with the world's own idea of the screen kept in step.
        func report(_ event: SearchPanelEvent) {
            switch event {
            case .opened: searchPanelIsVisible = true
            case .closed: searchPanelIsVisible = false
            case .answered, .openedMoment: break
            }
            searchPanelWatch?(event)
        }

        /// The user really presses the chord: the shortcut's own handler opens the panel, and *then*
        /// the tutorial's observer hears about the keypress — the order `GlobalShortcuts` delivers in.
        func pressActivityChord() {
            report(.opened)
            hotkeyWatch?()
        }

        /// Writes a real stamp through the real writer, into a temp file this test owns.
        func recordStamp(at: Double) throws {
            let url =
                stampURL
                ?? FileManager.default.temporaryDirectory
                    .appendingPathComponent("tutorial-resume-stamp-\(UUID().uuidString)")
                    .appendingPathComponent("last-query.json")
            stampURL = url
            try QueryStamp(tool: "recall", at: at).record(to: url)
        }
    }

    /// Satisfies whatever the current beat is waiting for, honestly, and moves on.
    private func stepForward(_ model: TutorialModel, _ world: World) throws {
        switch model.step.gate {
        case .userAction:
            model.advance()
        case .screenRecordingGrant:
            world.screenGranted = true
            model.poll()
            model.advance()
        case .realFrames:
            world.frameCount = TutorialModel.frameTarget
            model.poll()
            model.advance()
        case .realHotkey:
            world.pressActivityChord()
        case .realGesture:
            world.dragWatch?()
            model.advance()
        case .realSearchPanel:
            world.report(.opened)
        case .realSearchResult:
            world.report(.answered(query: "captured", results: 1))
            model.advance()
        case .genuineToolCall:
            try world.recordStamp(at: world.clock + 1)
            model.poll()
            model.advance()
        }
    }

    private func drive(_ model: TutorialModel, _ world: World, to destination: TutorialStep) throws {
        var guardrail = 0
        while model.step != destination, !model.step.isTerminal, guardrail < 40 {
            try stepForward(model, world)
            guardrail += 1
        }
        XCTAssertEqual(model.step, destination, "the flow did not reach \(destination)")
    }

    // MARK: - The record itself

    func testAFreshInstallHasNothingToResume() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        XCTAssertNil(
            TutorialResume(defaults: defaults).step,
            "nothing has been recorded, so there is no walkthrough to pick up")
    }

    func testTheBeatItRecordsIsTheBeatItAnswers() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        let resume = TutorialResume(defaults: defaults)
        for beat in TutorialStep.flow {
            resume.record(beat)
            XCTAssertEqual(resume.step, beat, "\(beat) has to survive the process that recorded it")
        }
    }

    /// `finished` and `skipped` are not places a user can stand. A record of one would reopen a
    /// walkthrough that is over, on a beat that tears itself down the instant it is entered.
    func testATerminalStateIsNeverAResumePoint() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        let resume = TutorialResume(defaults: defaults)
        resume.record(.menuBar)
        resume.record(.finished)
        XCTAssertEqual(resume.step, .menuBar, "a terminal state must not overwrite a real beat")

        defaults.set(TutorialStep.skipped.rawValue, forKey: TutorialResume.key)
        XCTAssertNil(resume.step, "and one already on disk is not read back")
    }

    /// The downgrade case: a later build recorded a beat this one does not have. Starting the
    /// walkthrough over is a small cost; starting it on the wrong beat is a bug nobody can read.
    func testAnUnreadableTokenIsNotAGuess() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        defaults.set("a-beat-from-a-later-build", forKey: TutorialResume.key)
        XCTAssertNil(TutorialResume(defaults: defaults).step)
    }

    // MARK: - What the run writes

    func testEveryBeatIsRecordedAsItIsEntered() throws {
        let world = World()
        world.screenGranted = true
        let model = TutorialModel(environment: world.environment())

        model.begin()
        try drive(model, world, to: .menuBar)

        XCTAssertEqual(
            world.recorded,
            [
                .invitation, .collectFrames, .openActivity, .timeline, .findMoments, .query,
                .claudeHandoff, .claudeProof, .allSet, .menuBar,
            ],
            "the record has to follow the flow beat for beat, or a relaunch resumes somewhere else")
    }

    func testFinishingTheRunSpendsTheRecord() throws {
        let world = World()
        world.screenGranted = true
        let model = TutorialModel(environment: world.environment())

        model.begin()
        try drive(model, world, to: .menuBar)
        model.advance()

        XCTAssertEqual(model.step, .finished)
        XCTAssertEqual(
            world.clears, 1,
            "a record left behind after the last card reopens the walkthrough on every launch")
    }

    func testTheUserEndingTheWalkthroughSpendsTheRecord() {
        let world = World()
        let model = TutorialModel(environment: world.environment())

        model.begin()
        model.skip()

        XCTAssertEqual(model.step, .skipped)
        XCTAssertEqual(world.clears, 1, "they said no; putting it back tomorrow is not an answer")
    }

    /// **The defect this whole change is about.**
    ///
    /// `applicationWillTerminate` calls `Tutorial.abandon()` so the borderless overlays and the
    /// menu-bar spotlight do not survive the process that owns them. While that was a synonym for
    /// `skip()`, the teardown also spent the record — so the one process death the flow *asks macOS
    /// for* was the one that made the walkthrough unrecoverable.
    func testAProcessDyingUnderTheRunKeepsTheRecordAndStillTearsDown() {
        let world = World()
        let model = TutorialModel(environment: world.environment())

        model.begin()
        model.advance()  // invitation → screenAccess
        XCTAssertEqual(model.step, .screenAccess)

        model.abandon()

        XCTAssertEqual(model.step, .skipped, "the machine still stops")
        XCTAssertEqual(world.clears, 0, "nobody decided to end this run, so the beat survives it")
        XCTAssertEqual(world.recorded.last, .screenAccess, "and it is the beat they were on")
        XCTAssertEqual(world.overlayDismissals, 1, "the card cannot outlive the process")
        XCTAssertEqual(world.spotlightHides, 1, "nor the spotlight")
    }

    // MARK: - What the next process does with it

    func testARelaunchPicksUpOnTheBeatItRecorded() {
        let world = World()
        world.screenGranted = true
        let model = TutorialModel(environment: world.environment())

        model.begin(resumingAt: .timeline)

        XCTAssertEqual(model.step, .timeline)
        XCTAssertEqual(
            world.overlayPresented, [.timeline],
            "the run that comes back must not replay the cards the user already walked")
    }

    /// **The designed-for death, end to end.**
    ///
    /// The run died on `screenAccess` because macOS offered "Quit & Reopen", and the successor
    /// launches *with* the grant. Landing on the recorded beat would ask somebody for a permission
    /// they gave thirty seconds ago; the world is re-read instead and the run picks up at the beat
    /// that grant was for.
    func testAResumedRunRereadsTheWorldRatherThanTrustingTheBeatItWokeOn() {
        let granted = World()
        granted.screenGranted = true
        let resumed = TutorialModel(environment: granted.environment())
        resumed.begin(resumingAt: .screenAccess)

        XCTAssertGreaterThan(granted.screenReads, 0, "a resumed run asks the system, every time")
        XCTAssertEqual(
            resumed.step, .collectFrames,
            "the grant arrived while the app was away; asking for it again is the flow being deaf")
        XCTAssertFalse(
            resumed.plan.contains(.screenAccess),
            "and the beat is out of this run's plan entirely, exactly as it is on a fresh start")

        // The same record, on a machine where the grant did *not* survive — a user who pressed
        // "Quit & Reopen" and then declined, or who quit before answering at all.
        let ungranted = World()
        let stillAsking = TutorialModel(environment: ungranted.environment())
        stillAsking.begin(resumingAt: .screenAccess)

        XCTAssertEqual(
            stillAsking.step, .screenAccess,
            "nothing about the record decided this; the answer came from the world both times")
    }

    /// The other half of re-reading the world, and the one a resume could quietly get wrong: the run
    /// woke up *past* the screen beat on a machine that cannot see the screen. Whatever happened in
    /// the process that died, that is a run which walked past the grant without it — so the beat that
    /// waits for frames says so immediately rather than sitting out a patience for captures that
    /// physically cannot arrive, and it does not open a browser page for somebody whose screen this
    /// app cannot see.
    func testAResumedRunPastTheScreenBeatWithNoGrantKnowsItCannotSee() {
        let world = World()
        world.screenGranted = false
        let model = TutorialModel(environment: world.environment())

        model.begin(resumingAt: .collectFrames)

        XCTAssertEqual(model.step, .collectFrames)
        XCTAssertTrue(model.didWaiveScreenAccess, "re-derived from TCC, not restored from a record")
        XCTAssertTrue(model.waiverIsOffered, "there is no waiting this out; nothing can arrive")
        XCTAssertEqual(model.outcome, .cannotSee)
        XCTAssertTrue(
            world.pagesOpened.isEmpty,
            "a page opened to be captured is a window nobody asked for when nothing can be captured")
    }

    /// The search beats hold state a resumed run cannot inherit: the panel was on screen in the
    /// process that died and is on nobody's screen now.
    func testAResumedSearchBeatDoesNotInheritAPanelFromTheRunThatDied() {
        let world = World()
        world.screenGranted = true
        let model = TutorialModel(environment: world.environment())

        model.begin(resumingAt: .findMoments)

        XCTAssertEqual(model.step, .findMoments)
        XCTAssertFalse(
            model.searchPanelIsOpen,
            "the panel belonged to a process that is gone; the beat waits for a real press")
        XCTAssertFalse(model.gateIsSatisfied)
    }

    /// **The one beat a resumed run may not land on**, and it is a correctness rule rather than a
    /// nicety: `claudeProof` waits for a `QueryStamp` written strictly after an instant its
    /// *predecessor* snapshots. A run woken straight onto it would be watching from instant zero, and
    /// a stamp from the session that just ended would read as the payoff.
    func testAResumedProofBeatGoesBackToTheHandoffThatStartsItsWatch() throws {
        let world = World()
        world.screenGranted = true
        // Claude called one of our tools during the run that died.
        try world.recordStamp(at: world.clock - 100)

        let model = TutorialModel(environment: world.environment())
        model.begin(resumingAt: .claudeProof)

        XCTAssertEqual(model.step, .claudeHandoff, "the beat that starts the watch comes first")

        model.advance()
        XCTAssertEqual(model.step, .claudeProof)
        model.poll()
        XCTAssertNil(
            model.proof,
            "a tool call from the session that ended is not proof for the session that resumed")
        XCTAssertFalse(model.gateIsSatisfied)

        // …and the beat is still winnable, honestly, by a call made now.
        try world.recordStamp(at: world.clock + 1)
        model.poll()
        XCTAssertNotNil(model.proof, "a real call after the resume still pays off")
    }

    /// A record that cannot be placed starts the walkthrough over rather than guessing — the same
    /// answer `TutorialResume` gives to a token it cannot read.
    func testAnUnplaceableRecordStartsAtTheTop() {
        let world = World()
        let model = TutorialModel(environment: world.environment())

        model.begin(resumingAt: .finished)

        XCTAssertEqual(model.step, .invitation)
    }

    // MARK: - Where a launch lands

    /// The ordering, which is the whole of the launch decision.
    ///
    /// Onboarding first because the walkthrough is what its last card hands off to: a machine holding
    /// both records is one where the earlier flow never finished.
    func testAnUnfinishedSetupOutranksAnInterruptedWalkthrough() {
        XCTAssertEqual(
            ContextAppDelegate.landing(
                onboarded: false, onboardingInProgress: false, tutorialResume: .timeline),
            .onboarding)
        XCTAssertEqual(
            ContextAppDelegate.landing(
                onboarded: true, onboardingInProgress: true, tutorialResume: .timeline),
            .onboarding)
    }

    /// And the clause this change adds. It is an `else` rather than a second thing to do: opening the
    /// Activity panel *is* the gesture `findMoments` waits for, so a launch that did both would credit
    /// the user with a press they never made.
    func testAnInterruptedWalkthroughOutranksTheActivityPanel() {
        XCTAssertEqual(
            ContextAppDelegate.landing(
                onboarded: true, onboardingInProgress: false, tutorialResume: .findMoments),
            .tutorial(.findMoments))
    }

    /// **The walkthrough is what the "Quit & Reopen" mechanism was always for**, one flow later.
    ///
    /// `ContextAppDelegate.shouldReviveAfterTermination` brings the app back when macOS ends a run
    /// nobody asked it to end — measured against exactly this alert. Its second input was read as
    /// "onboarding has a resume point", and by the time the tutorial asks for Screen Recording the
    /// last card of onboarding has already spent that record. So the app stayed dead, mid-walkthrough,
    /// in the same shape as the original report.
    func testAWalkthroughOnItsOwnIsARunWorthComingBackTo() {
        XCTAssertTrue(
            ContextAppDelegate.aRunIsWaiting(onboardingResume: nil, tutorialResume: .screenAccess),
            "the beat that asks macOS for the quit is the beat that most needs to survive it")
        XCTAssertTrue(
            ContextAppDelegate.aRunIsWaiting(onboardingResume: .permissions, tutorialResume: nil),
            "and the flow this was written for still counts")
        XCTAssertFalse(
            ContextAppDelegate.aRunIsWaiting(onboardingResume: nil, tutorialResume: nil),
            "a user with nothing outstanding has nothing to lose by staying quit")
    }

    func testNothingOutstandingOpensTheApp() {
        XCTAssertEqual(
            ContextAppDelegate.landing(
                onboarded: true, onboardingInProgress: false, tutorialResume: nil),
            .activity)
    }

    // MARK: - The card the second run drives

    /// **The overlay's window outlives a run; the card's binding must not.**
    ///
    /// The window and its hosting view are built once and kept, and the card inside is bound to
    /// whichever `TutorialModel` built it. A second walkthrough — which is exactly what a resume is —
    /// would otherwise go on rendering, and go on driving, the machine that already finished: an empty
    /// card whose buttons answer nothing. Asserted through the root view rather than through the
    /// reference the overlay keeps beside it, because that is the only place the two can disagree.
    func testASecondWalkthroughRebindsTheCardToTheNewMachine() throws {
        try XCTSkipIf(NSScreen.screens.isEmpty, "the overlay places itself against a real display")

        let world = World()
        let first = TutorialModel(environment: world.environment())
        let second = TutorialModel(environment: World().environment())
        let overlay = TutorialOverlay.shared
        defer { overlay.hide() }

        // A beat that does not take focus, so a suite run does not activate this app over whatever
        // the developer is doing (`TutorialStep.takesFocusOnEntry`).
        overlay.show(model: first, step: .claudeProof)
        XCTAssertTrue(overlay.machineOnScreen === first)

        overlay.show(model: second, step: .claudeProof)
        XCTAssertTrue(
            overlay.machineOnScreen === second,
            "the resumed run's card was still bound to the run that finished")
    }
}
