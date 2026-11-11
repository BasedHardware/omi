import AppKit
import ContextCore
import SwiftUI
import XCTest

@testable import ContextApp

/// The tutorial's step machine, tested where the product's credibility actually sits: that nothing it
/// claims can be produced by time passing, by an empty search, or by this app alone — and that
/// leaving it, from any step, takes everything it put on screen back off.
///
/// Since the cards stopped narrating the machinery, the *words* are tested here too. Hiding a
/// mechanism is only safe if the sentence that replaced it is still a consequence of what happened,
/// so `speech` and `outcome` are asserted alongside the gates rather than trusted.
///
/// No window is created anywhere in here. `TutorialModel` holds no `NSWindow` precisely so these
/// assertions can be about behaviour rather than about a screen.
@MainActor
final class TutorialTests: XCTestCase {

    // MARK: - Harness

    /// Records every side effect the model asks for, and lets a test answer the world however it
    /// likes. The clock is a variable so a test can move time without waiting for it.
    @MainActor
    private final class World {
        var clock: Double = 1_700_000_000
        var frameCount = 0
        var framesAskedSince: [Double] = []
        var screenGranted = false
        /// Whether that grant belongs to the next process rather than this one. False by default,
        /// which is the state every test written before this beat existed was written for.
        var screenPendingRelaunch = false
        var stampURL: URL?
        /// Starts closed. Nothing in this app opens a timeline until something opens it, and a world
        /// that begins with one already up would let a beat read a window it never caused.
        var timelineIsVisible = false
        /// The same rule for the search panel, and it matters more here: the beat that waits for one
        /// is satisfied by it *appearing*, so a world that started with it up would satisfy that gate
        /// before the user had touched anything.
        var searchPanelIsVisible = false
        var searchPanelPresentations = 0
        var searchPanelDismissals = 0

        /// What the world answers when the tutorial hands the first question over. The happy path by
        /// default; every test that cares about a failing handoff sets its own.
        var claudeAnswer: TutorialClaudeAsk? = .prompted(restarted: false, mayNotReachMe: false)
        var claudeAsks: [String] = []
        /// The consent answer each ask carried, so a test can assert nothing agreed to a restart on
        /// the user's behalf.
        var claudeAsksRestartingFirst: [Bool] = []
        /// Whether a Claude is open that predates our MCP config.
        var claudeNeedsRestart = false

        /// Every page the tutorial asked the world to open, in order, and whether the world would
        /// take them. Both matter: the capture beat's card claims a page was opened, and the claim
        /// has to follow the answer rather than the attempt.
        var pagesOpened: [URL] = []
        var pageWillOpen = true

        /// Where Claude's window is, for the beats whose card has to stand clear of it. Nil is the
        /// ordinary state — Claude is not running when the tutorial starts.
        var claudeWindow: CGRect?
        var claudeWindowLookups = 0

        /// Whether the machine is genuinely listening for the chord that opens Activity.
        var chordIsArmed = true
        /// The shortcut as the shortcut layer *prints* it, which is the only thing the tutorial ever
        /// learns about it. A repeated tap by default, so every test written before the beat grew a
        /// second drawing still exercises the branch it was written for; the tests about the launch
        /// gesture set it to the pair's spelling themselves.
        var chord = "⌘⌘"
        /// Whether a timeline window actually comes up when something opens one. False models the
        /// shell declining because the capture store is not open yet.
        var timelineCanOpen = true

        var overlayPresented: [TutorialStep] = []
        var overlayDismissals = 0
        var timelinePresentations = 0
        var timelineDismissals = 0
        var spotlightShows = 0
        var spotlightHides = 0
        var musicStarts = 0
        var musicStops = 0
        var clicks = 0
        var chimes = 0

        /// The two watchers, as the model armed them. Held rather than counted so a test can fire
        /// the *real* callback — which is the only way anything sets the gates they feed.
        var hotkeyWatch: (() -> Void)?
        var dragWatch: (() -> Void)?
        /// The search panel's observer, as the model armed it. Held for the same reason the other two
        /// are: the only honest way to satisfy the search gates is to send the model the events the
        /// real panel sends, through the callback the model itself registered.
        var searchPanelWatch: ((SearchPanelEvent) -> Void)?

        func environment() -> TutorialEnvironment {
            var environment = TutorialEnvironment()
            environment.pollInterval = nil
            environment.now = { self.clock }
            environment.frameCount = { since in
                self.framesAskedSince.append(since)
                return self.frameCount
            }
            environment.screenIsGranted = { self.screenGranted }
            environment.screenNeedsRelaunch = { self.screenPendingRelaunch }
            environment.openPage = { url in
                self.pagesOpened.append(url)
                return self.pageWillOpen
            }
            environment.claudeWindowFrame = {
                self.claudeWindowLookups += 1
                return self.claudeWindow
            }
            environment.askClaude = { question, restartingFirst, answer in
                self.claudeAsks.append(question)
                self.claudeAsksRestartingFirst.append(restartingFirst)
                if let outcome = self.claudeAnswer { answer(outcome) }
            }
            environment.claudeRestartIsNeeded = { self.claudeNeedsRestart }
            environment.activityChord = { self.chord }
            environment.activityChordIsArmed = { self.chordIsArmed }
            environment.watchForActivityHotkey = { self.hotkeyWatch = $0 }
            environment.stopWatchingActivityHotkey = { self.hotkeyWatch = nil }
            environment.watchForDrag = { self.dragWatch = $0 }
            environment.stopWatchingDrag = { self.dragWatch = nil }
            environment.presentTimeline = {
                self.timelinePresentations += 1
                self.timelineIsVisible = self.timelineCanOpen
            }
            environment.dismissTimeline = { self.timelineDismissals += 1 }
            environment.timelineIsVisible = { self.timelineIsVisible }
            environment.watchSearchPanel = { self.searchPanelWatch = $0 }
            environment.stopWatchingSearchPanel = { self.searchPanelWatch = nil }
            environment.searchPanelIsVisible = { self.searchPanelIsVisible }
            environment.presentSearchPanel = {
                self.searchPanelPresentations += 1
                self.reportFromTheSearchPanel(.opened)
            }
            environment.dismissSearchPanel = {
                self.searchPanelDismissals += 1
                self.reportFromTheSearchPanel(.closed)
            }
            environment.locateTarget = { _ in nil }
            environment.presentOverlay = { self.overlayPresented.append($0) }
            environment.dismissOverlay = { self.overlayDismissals += 1 }
            environment.showMenuBarSpotlight = { self.spotlightShows += 1 }
            environment.hideMenuBarSpotlight = { self.spotlightHides += 1 }
            environment.newToolCall = { since in
                guard let url = self.stampURL else { return nil }
                return QueryStamp.newCall(since: since, from: url)
            }
            environment.playClick = { self.clicks += 1 }
            environment.playSwoosh = {}
            environment.playChime = { self.chimes += 1 }
            environment.startMusic = { self.musicStarts += 1 }
            environment.stopMusic = { self.musicStops += 1 }
            return environment
        }

        /// The user really presses the chord.
        ///
        /// Modelled the way it happens: the shortcut layer delivers to the app's own handler, which
        /// opens the **Activity search panel**, and *then* to the tutorial's observer — the order
        /// `GlobalShortcuts.deliver` really uses. Nothing here reaches into the model to set a flag —
        /// the only route in is the callback the model itself armed, which is what makes this beat's
        /// gate a fact about the user.
        ///
        /// It used to open a timeline here, because that is what the chord did. Repointing it at the
        /// search panel is what this world has to model now, and it is why the beat after it can no
        /// longer assume a timeline anybody opened — and why it has a panel to take away.
        func pressActivityChord() {
            guard let fired = hotkeyWatch else { return }
            reportFromTheSearchPanel(.opened)
            fired()
        }

        /// The user really drags, far enough for `TutorialDrag` to call it a gesture.
        func dragAcrossTheTimeline() {
            dragWatch?()
        }

        /// The real search panel says what it just did.
        ///
        /// Modelled the way it happens: the shell's `onSearch` opens `SearchBarWindow` — the tutorial
        /// does not take the press any more — and the panel then announces itself through
        /// `SearchPanelWatch`. Nothing here reaches into the model, which is what makes the search
        /// beats' gates facts about the panel rather than about the tutorial.
        func reportFromTheSearchPanel(_ event: SearchPanelEvent) {
            switch event {
            case .opened: searchPanelIsVisible = true
            case .closed: searchPanelIsVisible = false
            case .answered, .openedMoment: break
            }
            searchPanelWatch?(event)
        }

        /// The user clicks the real "Search All" pill, which opens the real panel.
        func pressTheSearchPill() {
            reportFromTheSearchPanel(.opened)
        }

        /// They type a question into the real bar and it really answers.
        func searchInTheRealPanel(_ query: String, results: Int) {
            reportFromTheSearchPanel(.answered(query: query, results: results))
        }
    }

    private func makeModel(_ world: World) -> TutorialModel {
        TutorialModel(environment: world.environment())
    }

    /// Satisfies whatever the current step is waiting for, honestly — the same inputs the real world
    /// would supply — and moves on.
    private func stepForward(_ model: TutorialModel, _ world: World) {
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
            // The keypress is the transition; there is no button to press afterwards.
            world.pressActivityChord()
        case .realGesture:
            world.dragAcrossTheTimeline()
            model.advance()
        case .realSearchPanel:
            // The click on the real pill is the transition; there is no button to press afterwards.
            world.pressTheSearchPill()
        case .realSearchResult:
            // The real panel answering fills the gate. Leaving the step is still the button's job,
            // and the button still checks.
            world.searchInTheRealPanel("captured", results: 1)
            model.advance()
        case .genuineToolCall:
            recordStamp(world, at: world.clock + 1)
            model.poll()
            model.advance()
        }
    }

    private func drive(_ model: TutorialModel, _ world: World, to destination: TutorialStep) {
        model.begin()
        var guardrail = 0
        while model.step != destination, !model.step.isTerminal {
            stepForward(model, world)
            guardrail += 1
            XCTAssertLessThan(guardrail, 40, "the flow did not reach \(destination)")
            if guardrail >= 40 { return }
        }
    }

    /// Writes a real stamp through the real writer, into a temp file this test owns.
    private func recordStamp(_ world: World, tool: String = "recall", at: Double) {
        let url = world.stampURL ?? {
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("tutorial-stamp-\(UUID().uuidString)")
                .appendingPathComponent("last-query.json")
            world.stampURL = url
            return url
        }()
        XCTAssertNoThrow(try QueryStamp(tool: tool, at: at).record(to: url))
    }

    // MARK: - Ordering

    /// Also the guard on what the flow does *not* contain: a beat whose whole job is to announce the
    /// next beat, or a second card between two that belong together, would land in this list and
    /// fail here. (Opening a page is not a beat and never was one — it is something `collectFrames`
    /// does on entry, which is why the list did not move when the page came back.)
    func testTheFlowWalksEveryBeatInOrder() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)

        var visited: [TutorialStep] = []
        model.begin()
        visited.append(model.step)
        var guardrail = 0
        while !model.step.isTerminal, guardrail < 40 {
            stepForward(model, world)
            visited.append(model.step)
            guardrail += 1
        }

        XCTAssertEqual(
            visited,
            [
                .invitation, .collectFrames, .openActivity, .timeline, .findMoments, .query,
                .claudeHandoff, .claudeProof, .allSet, .menuBar, .finished,
            ],
            "the tutorial's order is the lesson; a reordering has to be deliberate")
        XCTAssertEqual(model.step, .finished)
    }

    /// The screen grant is asked for "at the right moment", which includes not asking at all.
    func testScreenAccessIsDroppedFromThePlanWhenItIsAlreadyGranted() {
        let granted = World()
        granted.screenGranted = true
        let withGrant = makeModel(granted)
        withGrant.begin()
        XCTAssertFalse(withGrant.plan.contains(.screenAccess))

        let missing = World()
        let withoutGrant = makeModel(missing)
        withoutGrant.begin()
        XCTAssertTrue(withoutGrant.plan.contains(.screenAccess))
        XCTAssertEqual(withoutGrant.plan.count, TutorialStep.flow.count)
    }

    func testTheScreenStepWaitsForTheRealGrantAndNotForAButton() {
        let world = World()
        let model = makeModel(world)
        drive(model, world, to: .screenAccess)

        XCTAssertFalse(model.advance(), "no grant, no advance")
        XCTAssertEqual(model.step, .screenAccess)

        world.screenGranted = true
        model.poll()
        XCTAssertTrue(model.gateIsSatisfied)
        XCTAssertTrue(model.advance())
        XCTAssertEqual(model.step, .collectFrames)
    }

    // MARK: - A grant that belongs to the next process

    /// **The ordinary first run, and a gate nothing the user does could satisfy.**
    ///
    /// macOS decides what a program may capture when that program connects to the window server, so a
    /// Screen Recording grant made while this app is running reads back as granted and captures
    /// nothing at all until the app starts again. That is not an edge case here: onboarding's
    /// permissions card is where the grant is normally taken, and its tutorial hand-off leaves from
    /// the card *before* the one that offers the relaunch — so the ordinary path reaches this
    /// walkthrough with the grant in and the capture path dead.
    ///
    /// The capture beat then waited out its full 45 s patience for frames that physically could not
    /// arrive, under a card telling the user to keep scrolling a page it had opened for them.
    func testTheCaptureBeatDoesNotAskForFramesThatCannotArrive() {
        let world = World()
        world.screenGranted = true
        world.screenPendingRelaunch = true
        let model = makeModel(world)
        drive(model, world, to: .collectFrames)

        XCTAssertEqual(
            model.outcome, .cannotSeeYet,
            "a grant the window server has not handed this process captured nothing, and did not "
                + "“capture too little”")
        XCTAssertTrue(
            model.waiverIsOffered,
            "the way past is offered at once, exactly as it is for an unarmed chord and a timeline "
                + "that never opened — this beat cannot be earned on this machine")
        XCTAssertEqual(
            world.pagesOpened, [],
            "opening a page so there is something to capture, when nothing can be captured, is a "
                + "browser window nobody asked for")
        XCTAssertFalse(model.gateIsSatisfied)
    }

    /// And the sentence, which must not be the one that asks for a scroll — nor the one that says a
    /// user who granted the permission has kept it switched off.
    func testTheCaptureBeatSaysWhyNothingCanArriveRatherThanAskingAgain() {
        let world = World()
        world.screenGranted = true
        world.screenPendingRelaunch = true
        let model = makeModel(world)
        drive(model, world, to: .collectFrames)

        let said = model.speech.everythingSaid
        XCTAssertTrue(said.contains("cannot see your screen yet"), said)
        XCTAssertTrue(said.contains("only hands that to me when I start"), said)
        XCTAssertFalse(said.lowercased().contains("scroll"), "it is still asking for the gesture")
        XCTAssertFalse(
            said.contains("kept"),
            "this user switched it on; telling them they declined reads their answer back wrong")

        // And the closing card carries the same fact rather than "nothing arrived".
        XCTAssertTrue(model.waive())
        drive(model, world, to: .allSet)
        XCTAssertEqual(model.outcome, .cannotSeeYet)
        XCTAssertTrue(
            model.speech.everythingSaid.contains("reopen me"),
            "the one thing the user can actually do about it is the thing to say")
    }

    /// The screen beat's own thank-you. A grant and a grant *in force* are not the same thing, and
    /// "Now I can see what you see" is the flattest possible version of the lie this flow is built
    /// against.
    func testTheScreenBeatDoesNotClaimSightItDoesNotHaveYet() {
        let world = World()
        let model = makeModel(world)
        model.begin()
        XCTAssertEqual(model.step, .invitation)
        XCTAssertTrue(model.advance())
        XCTAssertEqual(model.step, .screenAccess)

        world.screenGranted = true
        world.screenPendingRelaunch = true
        model.poll()

        XCTAssertTrue(model.gateIsSatisfied, "the grant is real and the beat is over")
        let said = model.speech.everythingSaid
        XCTAssertTrue(said.contains("Thank you"), said)
        XCTAssertTrue(said.contains("until I am reopened"), said)
        XCTAssertFalse(said.contains("Now I can see what you see"), said)
    }

    /// The grant that *is* in force still gets the sentence it always had — the branch above cannot
    /// have been bought by making every grant sound provisional.
    func testAGrantInForceStillSaysItCanSee() {
        let world = World()
        let model = makeModel(world)
        model.begin()
        XCTAssertTrue(model.advance())
        world.screenGranted = true
        model.poll()

        XCTAssertTrue(model.speech.everythingSaid.contains("Now I can see what you see"))
    }

    // MARK: - The capture beat, whose mechanism is now hidden

    /// The whole of the capture gate. A beat that could be satisfied by waiting would make every
    /// other claim this app makes suspect — and it is now the *only* thing holding that line, because
    /// the card no longer shows a number the user could check it against.
    func testTheCaptureBeatReflectsTheStoreAndNeverElapsedTime() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .collectFrames)

        // Ten minutes and a hundred ticks with an empty store.
        for _ in 0..<100 {
            world.clock += 6
            model.poll()
        }
        XCTAssertEqual(model.framesCollected, 0)
        XCTAssertFalse(model.gateIsSatisfied)
        XCTAssertFalse(model.advance(), "time passing is not a frame")
        XCTAssertEqual(model.step, .collectFrames)
        XCTAssertEqual(model.outcome, .waiting)

        // Frames genuinely land.
        world.frameCount = TutorialModel.frameTarget
        model.poll()
        XCTAssertEqual(model.framesCollected, TutorialModel.frameTarget)
        XCTAssertEqual(model.outcome, .caught)
        XCTAssertTrue(model.advance())
        XCTAssertEqual(model.step, .openActivity)
    }

    /// The sentence the user reads is a consequence of the store, not of the step being on screen.
    /// Ten minutes of ticking must not turn the waiting line into "got it".
    ///
    /// The waiting line changed when this beat stopped telling people to "go and look at something"
    /// and started opening a page for them to scroll instead. The guard was never about that wording,
    /// so it is now asserted two ways: the exact line, and — the part that actually catches the bug —
    /// that a hundred idle ticks leave it *not* claiming success.
    func testTheCaptureBeatSaysGotItOnlyOnceItReallyHasIt() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .collectFrames)

        for _ in 0..<100 {
            world.clock += 6
            model.poll()
        }
        let waiting = model.speech
        XCTAssertEqual(waiting.lead, "I opened Anthropic's research page.")
        XCTAssertNotEqual(waiting.lead, "Got it.", "idling must never read as success")

        world.frameCount = TutorialModel.frameTarget
        model.poll()
        XCTAssertEqual(model.speech.lead, "Got it.")
        XCTAssertNotEqual(model.speech, waiting, "the line has to change when the fact does")
    }

    func testFramesAreCountedOnlyFromTheMomentTheStepBegan() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        world.clock = 1_700_000_500
        drive(model, world, to: .collectFrames)

        XCTAssertFalse(world.framesAskedSince.isEmpty)
        XCTAssertTrue(
            world.framesAskedSince.allSatisfy { $0 == 1_700_000_500 },
            "frames from before this step cannot count towards this step")
    }

    func testTheWayForwardWithoutFramesIsOfferedLateAndSaysWhatDidNotHappen() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .collectFrames)

        XCTAssertFalse(model.waiverIsOffered, "the escape hatch must not appear immediately")
        XCTAssertFalse(model.waive())

        world.clock += TutorialModel.framePatience + 1
        XCTAssertTrue(model.waiverIsOffered)
        XCTAssertTrue(model.waive())
        XCTAssertEqual(model.step, .openActivity)
        XCTAssertTrue(model.didWaiveFrames)
        XCTAssertEqual(model.outcome, .nothingArrived)

        drive(model, world, to: .allSet)
        XCTAssertEqual(model.outcome, .nothingArrived, "a waived beat is not a caught one")
        XCTAssertEqual(model.speech.aside, TutorialOutcome.nothingArrived.sentence)
        XCTAssertNotEqual(
            model.speech.aside, TutorialOutcome.caught.sentence,
            "a waived step must not be reported as a success")
    }

    func testAWaivedCaptureBeatNeverClaimsTheScreenIsSearchable() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .collectFrames)
        world.frameCount = TutorialModel.frameTarget - 1
        model.poll()
        world.clock += TutorialModel.framePatience + 1
        XCTAssertTrue(model.waive())

        XCTAssertEqual(model.outcome, .tooLittleArrived)
        drive(model, world, to: .allSet)
        XCTAssertFalse(
            model.speech.everythingSaid.contains("searchable"),
            "one frame short of the gate is not a searchable screen: \(model.speech.everythingSaid)")
    }

    /// The closing card's success sentence, from every direction. Only one of them reaches it, and it
    /// is the one where the store really answered — which is what makes `outcome` worth having as a
    /// value rather than as three `if`s inside a view.
    func testTheSuccessSentenceIsReachableOnlyFromARealFrameCount() {
        for landed in [0, 1, TutorialModel.frameTarget - 1] {
            let world = World()
            world.screenGranted = true
            let model = makeModel(world)
            drive(model, world, to: .collectFrames)
            world.frameCount = landed
            model.poll()
            world.clock += TutorialModel.framePatience + 1
            XCTAssertTrue(model.waive())
            drive(model, world, to: .allSet)
            XCTAssertNotEqual(
                model.speech.aside, TutorialOutcome.caught.sentence,
                "\(landed) frames must not close the tutorial as a success")
        }

        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .allSet)
        XCTAssertEqual(model.outcome, .caught)
        XCTAssertEqual(model.speech.aside, TutorialOutcome.caught.sentence)
    }

    // MARK: - The words

    /// The two things the cards must never put back: how long the tutorial is, and how many frames
    /// have landed. Read off the production copy through the production model, in every state the
    /// flow can be driven into, rather than off the source text.
    func testNoCardEverSpeaksAProgressCountOrAFrameCount() {
        var said: [String] = []

        // The grant path, both answers.
        let ungranted = World()
        let asking = makeModel(ungranted)
        drive(asking, ungranted, to: .screenAccess)
        said.append(asking.speech.everythingSaid)
        ungranted.screenGranted = true
        asking.poll()
        said.append(asking.speech.everythingSaid)

        // The main path, and both answers of every step that has two.
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        model.begin()
        var guardrail = 0
        while !model.step.isTerminal, guardrail < 40 {
            said.append(model.speech.everythingSaid)
            if model.step == .query {
                // Both the empty-handed lines as well as the found-it one: a real question that
                // found nothing, and the panel closed under the beat.
                world.searchInTheRealPanel("nothing captured matches this", results: 0)
                said.append(model.speech.everythingSaid)
                world.reportFromTheSearchPanel(.closed)
                said.append(model.speech.everythingSaid)
                world.reportFromTheSearchPanel(.opened)
            }
            stepForward(model, world)
            guardrail += 1
        }

        // The failure branches the happy path never visits.
        let dark = World()
        dark.screenGranted = true
        dark.timelineCanOpen = false
        let darkModel = makeModel(dark)
        drive(darkModel, dark, to: .timeline)
        said.append(darkModel.speech.everythingSaid)

        // The chord this machine cannot fire, and the handoff Claude would not take.
        let unarmed = World()
        unarmed.screenGranted = true
        unarmed.chordIsArmed = false
        let unarmedModel = makeModel(unarmed)
        drive(unarmedModel, unarmed, to: .openActivity)
        said.append(unarmedModel.speech.everythingSaid)

        // The consent beat, which only appears when a restart would cost the user something.
        let openClaude = World()
        openClaude.screenGranted = true
        openClaude.claudeNeedsRestart = true
        let openClaudeModel = makeModel(openClaude)
        drive(openClaudeModel, openClaude, to: .claudeHandoff)
        said.append(openClaudeModel.speech.everythingSaid)

        for outcome in [TutorialClaudeAsk.copiedInstead, .notInstalled] {
            let refused = World()
            refused.screenGranted = true
            refused.claudeAnswer = outcome
            let refusedModel = makeModel(refused)
            drive(refusedModel, refused, to: .claudeHandoff)
            said.append(refusedModel.speech.everythingSaid)
            XCTAssertTrue(refusedModel.advance())
            said.append(refusedModel.speech.everythingSaid)
        }

        let waived = World()
        waived.screenGranted = true
        let waivedModel = makeModel(waived)
        drive(waivedModel, waived, to: .collectFrames)
        waived.clock += TutorialModel.framePatience + 1
        XCTAssertTrue(waivedModel.waive())
        drive(waivedModel, waived, to: .allSet)
        said.append(waivedModel.speech.everythingSaid)

        XCTAssertGreaterThan(said.count, 10, "the walk has to have visited the whole flow")
        for line in said {
            XCTAssertFalse(
                line.contains(where: \.isNumber),
                "a card is counting something out loud: \(line)")
            for word in ["frame", "step ", " of ", "%", "progress"] {
                XCTAssertFalse(
                    line.localizedCaseInsensitiveContains(word),
                    "“\(word)” is the mechanism showing through: \(line)")
            }
        }
    }

    /// The mark leans on a run of its own sentence, never on a second copy of those words.
    func testEveryStressedRunIsPartOfTheLineItBelongsTo() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        model.begin()
        var guardrail = 0
        while !model.step.isTerminal, guardrail < 40 {
            let speech = model.speech
            if let stress = speech.stress {
                XCTAssertTrue(
                    speech.lead.contains(stress),
                    "“\(stress)” is not in “\(speech.lead)”, so the emphasis would silently vanish")
                XCTAssertEqual(
                    speech.runs.map(\.0).joined(), speech.lead,
                    "the runs have to reassemble into exactly the line")
            }
            stepForward(model, world)
            guardrail += 1
        }
    }

    // MARK: - The search, conducted in the real search panel

    /// **The regression this whole section is here for.**
    ///
    /// The pill beat used to advance on the press: `Tutorial.searchPillWasPressed()` answered true,
    /// the shell's guard swallowed it, and `SearchBarWindow` never opened — the user pressed a real
    /// control and was shown a tutorial-only imitation of results on a coach card. So the gate was a
    /// click and the surface was a copy.
    ///
    /// The gate is the panel now, and there is nothing in `TutorialModel` that can satisfy it: the
    /// only route to `.opened` is the real panel announcing itself. A press that fails to open one —
    /// which is what an intercepted press *is* — leaves the beat exactly where it was.
    func testThePillBeatWaitsForTheRealSearchPanelAndNotForThePress() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .findMoments)

        XCTAssertEqual(model.step.gate, .realSearchPanel)
        XCTAssertFalse(model.gateIsSatisfied, "nothing is on screen yet")
        XCTAssertFalse(model.advance(), "and no button may move past a panel that never came up")
        XCTAssertEqual(model.step, .findMoments)

        world.pressTheSearchPill()
        XCTAssertTrue(model.searchPanelIsOpen)
        XCTAssertEqual(model.step, .query, "the panel appearing is the transition")
    }

    /// **The chord's own panel is taken back before the drag beat, which is what leaves this gate a
    /// real question.**
    ///
    /// The whole reason the pill beat's gate can be "a panel is on screen" again. ⌘ + ⌘ opens the
    /// search panel, so the ordinary run reaches the drag beat with one the user summoned a second
    /// ago — floating over the very timeline they are about to be asked to drag, and still up when
    /// the beat that teaches people where search is begins. Left alone, that beat would satisfy
    /// itself on entry and vanish in the frame it appeared, which is exactly what happened while the
    /// search surface was a permanent window.
    ///
    /// So `TutorialStep.usesSearchPanel` closes it on the way into the drag beat, and the pill beat
    /// starts from nothing.
    func testTheChordsPanelIsTakenBackBeforeTheDragBeat() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .openActivity)

        world.pressActivityChord()

        XCTAssertEqual(model.step, .timeline)
        XCTAssertEqual(world.searchPanelDismissals, 1, "the panel the chord opened is still over the timeline")
        XCTAssertFalse(world.searchPanelIsVisible)
        XCTAssertFalse(model.searchPanelIsOpen)

        world.dragAcrossTheTimeline()
        XCTAssertTrue(model.advance(), "timeline → findMoments")
        XCTAssertEqual(model.step, .findMoments, "the pill beat was satisfied by the chord's own panel")
        XCTAssertFalse(model.gateIsSatisfied)

        world.pressTheSearchPill()
        XCTAssertEqual(model.step, .query)
    }

    /// …and the exception that read survives for: a panel that really is up when the beat begins.
    ///
    /// A user can press the chord again while reading the drag card. A beat waiting for something
    /// that has already happened is a beat that never ends, so the entry read stands — it is an
    /// exception again rather than the every-run default it became.
    func testThePillBeatIsSatisfiedOnEntryByAPanelThatIsGenuinelyAlreadyUp() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .timeline)

        // They press ⌘ + ⌘ again while reading the drag card, and this time nothing takes it away.
        world.pressTheSearchPill()
        XCTAssertEqual(model.step, .timeline, "a stray open during another beat must not move the flow")

        world.dragAcrossTheTimeline()
        XCTAssertTrue(model.advance(), "timeline → findMoments")
        XCTAssertEqual(
            model.step, .query,
            "a panel already on screen satisfies the pill beat on entry rather than stranding it")
    }

    /// The tutorial never consumes the press, which is what lets the real bar open at all.
    ///
    /// Asserted through the shell's own entry point, because that is the one the timeline calls:
    /// `ContextApp.swift` opens `SearchBarWindow` unless this answers true. It answers false with the
    /// tutorial stopped **and** with it running on the very beat that used to take the press.
    func testTheTutorialNeverTakesTheSearchPillPress() {
        XCTAssertFalse(
            Tutorial.searchPillWasPressed(),
            "the pill belongs to the timeline, in the tutorial as everywhere else")
    }

    /// The panel opening is not an answer. It reads the newest captures with nothing typed, and a
    /// gate that counted those rows would be satisfied by the bar merely existing — the "found it"
    /// beat would land on somebody who had not asked anything.
    func testTheOpeningReadOfThePanelDoesNotCountAsAFind() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        world.searchInTheRealPanel("", results: 60)
        XCTAssertEqual(model.resultCount, 60, "the panel really is showing sixty things")
        XCTAssertFalse(model.gateIsSatisfied, "and none of them was asked for")
        XCTAssertFalse(model.advance())
        XCTAssertEqual(model.speech.lead, "Type something you just looked at.")
    }

    func testARealQuestionThatFoundNothingStaysOnTheStepAndSaysSo() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        world.searchInTheRealPanel("something nobody captured", results: 0)
        XCTAssertEqual(model.step, .query, "no result, no “found it”")
        XCTAssertFalse(model.gateIsSatisfied)
        XCTAssertEqual(model.speech.lead, "Nothing matched that.")
        XCTAssertFalse(model.advance(), "the found-it line is not reachable by pressing continue")
        XCTAssertFalse(model.step.gate.isWaivable, "and it cannot be waived either")
    }

    func testARealResultTurnsTheCardIntoTheFoundItBeat() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        world.searchInTheRealPanel("invoice", results: 3)

        XCTAssertEqual(model.step, .query, "the found-it beat is the same card, changed")
        XCTAssertEqual(model.resultCount, 3)
        XCTAssertEqual(model.lastQuery, "invoice")
        XCTAssertEqual(model.speech.lead, "There it is.")
        XCTAssertEqual(model.speech.aside, "Click it to go back to that moment.")
        XCTAssertTrue(model.gateIsSatisfied)
        XCTAssertTrue(model.advance())
    }

    /// A second search that finds nothing takes the found-it line back off the card. The line is a
    /// statement about the current answer, not a badge the step earned once.
    func testAFailedSecondSearchWithdrawsTheFoundItLine() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        world.searchInTheRealPanel("captured", results: 2)
        XCTAssertEqual(model.speech.lead, "There it is.")

        world.searchInTheRealPanel("nothing at all", results: 0)
        XCTAssertEqual(model.speech.lead, "Nothing matched that.")
        XCTAssertFalse(model.gateIsSatisfied)
        XCTAssertFalse(model.advance())
    }

    /// Pressing a result in the real panel closes it — the timeline comes back at that moment, which
    /// is the payoff — so the card has to read the *travel*, not the empty screen it leaves behind.
    func testTravellingToAMomentIsWhatTheCardSaysAndNotThatThePanelWentAway() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)
        world.searchInTheRealPanel("captured", results: 2)

        world.reportFromTheSearchPanel(.openedMoment(at: 1_699_998_888, hasPicture: true))
        world.reportFromTheSearchPanel(.closed)

        XCTAssertFalse(model.searchPanelIsOpen)
        XCTAssertEqual(model.speech.lead, "There it is.")
        XCTAssertEqual(model.speech.aside, "That is the moment, exactly as it was.")
        XCTAssertTrue(model.gateIsSatisfied)
    }

    /// A moment with no surviving picture is said out loud rather than claimed.
    func testAMomentWithNoPictureIsAdmitted() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)
        world.searchInTheRealPanel("captured", results: 1)

        world.reportFromTheSearchPanel(.openedMoment(at: 1_699_998_888, hasPicture: false))
        XCTAssertEqual(
            model.speech.aside, "No picture survived that second — the words are what I still have.")
    }

    /// Escape on the panel with nothing found is a dead end unless the card says so and offers a way
    /// back — the gate cannot be waived, so there has to be one.
    func testAClosedPanelIsSaidOutLoudAndCanBeReopenedOnRequest() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        world.reportFromTheSearchPanel(.closed)
        XCTAssertFalse(model.searchPanelIsOpen)
        XCTAssertEqual(model.speech.lead, "The search bar is gone.")
        XCTAssertFalse(model.gateIsSatisfied)

        model.openSearchPanel()
        XCTAssertEqual(world.searchPanelPresentations, 1, "and only because the user asked")
        XCTAssertTrue(model.searchPanelIsOpen)
        XCTAssertEqual(model.speech.lead, "Type something you just looked at.")
    }

    /// The waiver on the pill beat has to *open* the panel, not skip past it: the beat after it has
    /// nothing to be asked in otherwise — and the card must then not congratulate the user on a click
    /// they never made.
    func testWaivingThePillBeatOpensTheRealPanelAndSaysWhoOpenedIt() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .findMoments)

        XCTAssertFalse(
            world.searchPanelIsVisible,
            "the chord's own panel is closed on the way into the drag beat, so this one starts empty")

        XCTAssertFalse(model.waiverIsOffered, "not before the patience has run")
        world.clock += TutorialModel.searchPanelPatience
        XCTAssertTrue(model.waiverIsOffered)
        XCTAssertTrue(model.waive())

        XCTAssertEqual(model.step, .query)
        XCTAssertTrue(model.didWaiveSearchPanel)
        XCTAssertEqual(world.searchPanelPresentations, 1)
        XCTAssertTrue(model.searchPanelIsOpen)
        XCTAssertEqual(model.speech.lead, "I opened the search bar for you.")
    }

    /// **The panel is the tutorial's furniture for two beats and nobody else's.**
    ///
    /// Leaving the search beats has to take it away, and the reason is what it is on screen: a 1112 pt
    /// floating slab carried into the Claude beats would be sitting over the very window those beats
    /// are about. The same rule is what takes the chord's own panel off the timeline before the drag
    /// beat — one property (`TutorialStep.usesSearchPanel`), both transitions.
    func testTheSearchPanelIsClosedOnTheWayOutOfTheSearchBeats() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)
        XCTAssertTrue(world.searchPanelIsVisible)
        let alreadyDismissed = world.searchPanelDismissals

        world.searchInTheRealPanel("captured", results: 1)
        XCTAssertTrue(model.advance(), "query → claudeHandoff")

        XCTAssertEqual(world.searchPanelDismissals, alreadyDismissed + 1)
        XCTAssertFalse(world.searchPanelIsVisible)
    }

    func testAbandoningTheTutorialMidSearchTakesThePanelWithIt() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)
        XCTAssertTrue(world.searchPanelIsVisible)
        let alreadyDismissed = world.searchPanelDismissals

        model.abandon()

        XCTAssertEqual(model.step, .skipped)
        XCTAssertEqual(world.searchPanelDismissals, alreadyDismissed + 1)
        XCTAssertFalse(world.searchPanelIsVisible)
    }

    /// **A panel the user closed themselves is not closed a second time on the way out.**
    ///
    /// The ownership half of the rule, and the only thing that keeps "the tutorial takes its own
    /// furniture away" from becoming "the tutorial closes whatever search surface it finds". A user
    /// who pressed Escape has said something, and a walkthrough that dismissed a window it did not
    /// put there — or dismissed the same one twice — is deciding for them.
    func testAPanelTheUserAlreadyClosedIsNotDismissedAgain() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        world.reportFromTheSearchPanel(.closed)
        let dismissalsAfterTheirOwn = world.searchPanelDismissals
        model.abandon()
        XCTAssertEqual(world.searchPanelDismissals, dismissalsAfterTheirOwn)
    }

    // MARK: - The Claude payoff

    /// The payoff gate, exercised through the production writer and reader.
    func testThePayoffCannotFireWithoutAGenuineToolCall() throws {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)

        // A stamp that was already on disk before the tutorial started watching.
        recordStamp(world, tool: "recall", at: world.clock - 600)
        drive(model, world, to: .claudeProof)

        for _ in 0..<50 {
            world.clock += 2
            model.poll()
        }
        XCTAssertNil(model.proof, "a stamp from an earlier session is not proof of this one")
        XCTAssertFalse(model.gateIsSatisfied)
        XCTAssertEqual(model.speech.lead, "Send it in Claude.", "and the card still waits")
        XCTAssertFalse(model.advance())
        XCTAssertEqual(model.step, .claudeProof)
        XCTAssertFalse(model.step.gate.isWaivable, "and there is no button that can stand in for it")

        // Claude really calls a tool.
        recordStamp(world, tool: "screen", at: world.clock + 1)
        model.poll()
        XCTAssertEqual(model.proof?.tool, "screen")
        XCTAssertEqual(model.speech.lead, "Claude just read your context.")
        XCTAssertTrue(model.advance())
        XCTAssertEqual(model.step, .allSet)
    }

    func testTheProofWatchStartsAtTheHandoffAndNotAtLaunch() throws {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .claudeHandoff)

        // A call served *before* the handoff, i.e. before the Claude we are about to restart could
        // possibly have read this store.
        recordStamp(world, tool: "recall", at: world.clock - 1)
        XCTAssertEqual(world.claudeAsks.count, 1)

        XCTAssertTrue(model.advance())
        model.poll()
        XCTAssertNil(model.proof, "the watch starts at the handoff, not at launch")
    }

    // MARK: - Skipping and teardown

    func testSkippingFromAnyStepIsTerminalAndLeavesNothingOnScreen() {
        for destination in TutorialStep.flow where destination != .screenAccess {
            let world = World()
            world.screenGranted = true
            let model = makeModel(world)
            drive(model, world, to: destination)
            XCTAssertEqual(model.step, destination, "could not reach \(destination)")

            let dismissalsBefore = world.overlayDismissals
            model.skip()

            XCTAssertEqual(model.step, .skipped, "skipping \(destination) must be terminal")
            XCTAssertGreaterThan(
                world.overlayDismissals, dismissalsBefore, "coach mark left up after \(destination)")
            XCTAssertGreaterThanOrEqual(world.spotlightHides, 1, "spotlight left up after \(destination)")
            XCTAssertEqual(world.musicStops, 1, "music left running after \(destination)")

            // The timeline is only dismissed if this run opened it — closing a window the tutorial
            // never opened would be taking away something the user did.
            let opened = TutorialStep.flow.firstIndex(of: destination)!
                >= TutorialStep.flow.firstIndex(of: .timeline)!
            XCTAssertEqual(
                world.timelineDismissals, opened ? 1 : 0,
                "timeline teardown wrong after \(destination)")

            // And a second skip changes nothing.
            model.skip()
            XCTAssertEqual(model.step, .skipped)
            XCTAssertEqual(world.musicStops, 1)
        }
    }

    func testSkippingTheScreenStepStillTearsDown() {
        let world = World()
        let model = makeModel(world)
        drive(model, world, to: .screenAccess)
        model.skip()
        XCTAssertEqual(model.step, .skipped)
        XCTAssertEqual(world.overlayDismissals, 1)
        XCTAssertEqual(world.musicStops, 1)
        XCTAssertEqual(world.timelineDismissals, 0)
    }

    func testFinishingTearsDownExactlyWhatSkippingDoes() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .menuBar)
        XCTAssertEqual(world.spotlightShows, 1, "the last beat rings the real status item")

        XCTAssertTrue(model.advance())
        XCTAssertEqual(model.step, .finished)
        XCTAssertEqual(world.overlayDismissals, 1)
        XCTAssertEqual(world.spotlightHides, 1)
        XCTAssertEqual(world.timelineDismissals, 1)
        XCTAssertEqual(world.musicStops, 1)
    }

    func testAbandonFromOutsideTheFlowIsTheSameTeardown() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .findMoments)
        model.abandon()
        XCTAssertEqual(model.step, .skipped)
        XCTAssertEqual(world.timelineDismissals, 1)
        XCTAssertEqual(world.overlayDismissals, 1)
        XCTAssertEqual(world.musicStops, 1)
    }

    func testATerminalStepDoesNothingWhenPoked() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        model.begin()
        model.skip()
        let overlays = world.overlayPresented.count
        XCTAssertFalse(model.advance())
        XCTAssertFalse(model.waive())
        model.poll()
        XCTAssertEqual(world.overlayPresented.count, overlays)
        XCTAssertEqual(model.step, .skipped)
    }

    // MARK: - Windows and sound

    func testTheTimelineIsOnlyDescribedAsOpenWhenItReallyOpened() {
        let world = World()
        world.screenGranted = true
        world.timelineCanOpen = false
        let model = makeModel(world)
        drive(model, world, to: .timeline)
        XCTAssertFalse(model.timelineIsOpen, "a window that did not appear must not be described")
        XCTAssertEqual(model.speech.lead, "The timeline did not open.")

        let second = World()
        second.screenGranted = true
        let openModel = makeModel(second)
        drive(openModel, second, to: .timeline)
        XCTAssertTrue(openModel.timelineIsOpen)
        XCTAssertEqual(openModel.speech.lead, "I opened your timeline.")
    }

    // MARK: - The chord, which the user has to press

    /// The whole of the second defect this beat exists to fix. The window used to open on its own
    /// the moment the step began, which taught nothing: the tutorial announced a shortcut and then
    /// did the shortcut's job. Now the step waits, and the only thing that satisfies it is the real
    /// shortcut layer delivering — the same delivery that opens the surface.
    ///
    /// **The surface it must not open itself is the search panel**, since that is what this chord
    /// opens. The old version of this test watched `timelinePresentations`, which no longer says
    /// anything about this beat at all: the chord does not reach the timeline, so a tutorial that
    /// opened one here would be cheating at a lesson nobody is being taught.
    func testTheChordBeatWaitsForTheRealShortcutAndOpensNothingItself() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .openActivity)

        // Five minutes of ticking on the step.
        for _ in 0..<100 {
            world.clock += 3
            model.poll()
        }
        XCTAssertEqual(
            world.searchPanelPresentations, 0,
            "the tutorial must not open the surface it is asking the user to open")
        XCTAssertEqual(world.timelinePresentations, 0, "and it must not open the other one either")
        XCTAssertFalse(model.hotkeyFired)
        XCTAssertFalse(model.gateIsSatisfied)
        XCTAssertFalse(model.advance(), "no keypress, no advance")
        XCTAssertEqual(model.step, .openActivity)

        // The user presses it. The shell's handler opens the Activity panel; the observer reports it.
        world.pressActivityChord()
        XCTAssertTrue(model.hotkeyFired)
        XCTAssertEqual(model.step, .timeline, "the keypress is the transition")
    }

    /// The honest way forward when the chord cannot fire at all: offered immediately, and labelled
    /// with what did not happen.
    ///
    /// **The waiver opens nothing now, and that is the change.** It used to have to — the chord
    /// opened the timeline, so a chord that could not fire left the next beat with no window — and
    /// the card then owned up to having opened it. The chord opens the Activity search panel, which
    /// is not what the next beat needs, and the timeline beat opens its own window whichever way this
    /// one ended: there is no fallback left to take, so the waiver records nothing and the beat after
    /// it reads identically either way.
    func testAChordThatCannotFireOffersTheWayOutAtOnceAndOpensNothingToCompensate() {
        let world = World()
        world.screenGranted = true
        world.chordIsArmed = false
        let model = makeModel(world)
        drive(model, world, to: .openActivity)

        XCTAssertTrue(model.waiverIsOffered, "a chord nothing is listening for is not a slow start")
        XCTAssertEqual(model.speech.lead, "I cannot listen for that shortcut.")
        XCTAssertEqual(
            model.speech.aside, "Accessibility is off, so those keys will not reach me.",
            "the card must not promise to open a window nothing here opens")
        XCTAssertEqual(world.searchPanelPresentations, 0)
        XCTAssertTrue(model.waive())

        XCTAssertEqual(model.step, .timeline)
        XCTAssertFalse(model.hotkeyFired, "waiving is not pressing")
        // The timeline the next beat needs was opened by that beat, not by this waiver.
        XCTAssertEqual(world.timelinePresentations, 1)
        XCTAssertEqual(model.speech.lead, "I opened your timeline.")
    }

    /// An armed chord gets the full wait before the escape hatch appears — otherwise the way out is
    /// on screen before anyone has had a chance to press anything.
    func testAnArmedChordIsGivenTimeBeforeTheWayOutAppears() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .openActivity)

        XCTAssertFalse(model.waiverIsOffered)
        XCTAssertFalse(model.waive())
        world.clock += TutorialModel.hotkeyPatience + 1
        XCTAssertTrue(model.waiverIsOffered)
    }

    /// The watcher is not left running over the rest of the tutorial.
    func testTheShortcutWatcherIsArmedForItsStepAndTornDownAfterIt() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .openActivity)
        XCTAssertNotNil(world.hotkeyWatch, "the step that needs it arms it")

        world.pressActivityChord()
        XCTAssertNil(world.hotkeyWatch, "and leaving the step takes it back down")

        model.skip()
        XCTAssertNil(world.dragWatch, "teardown stops every watcher")
    }

    // MARK: - The drag, which the user has to make

    /// **The drag beat opens its own timeline, and says so.**
    ///
    /// The regating this whole change turns on. The beat used to ride the chord: ⌘ + ⌘ opened the
    /// timeline, the user's keypress put it on screen, and the card's opening line took care not to
    /// claim credit for a window the tutorial had opened on the one branch where it had. The chord
    /// opens the Activity search panel now, so nothing before this beat produces a timeline — a
    /// version of this flow that left the beat alone would ask somebody to drag through a window that
    /// is not there.
    ///
    /// **The panel going back to being dismissible does not change that.** It closes on Escape and it
    /// closes when a result hands off to the timeline — but that hand-off is the *query* beat's
    /// payoff, two beats after this one, so it is still the tutorial or nothing here.
    ///
    /// So: exactly one presentation, made by this beat, on the ordinary path where the user really
    /// pressed the chord — and one sentence, which names who opened it.
    func testTheDragBeatOpensTheTimelineItselfAndSaysSo() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .openActivity)
        XCTAssertEqual(world.timelinePresentations, 0, "nothing before this beat opens a timeline")

        world.pressActivityChord()

        XCTAssertEqual(model.step, .timeline)
        XCTAssertEqual(
            world.timelinePresentations, 1,
            "the beat that asks for a drag has to put something on screen to drag")
        XCTAssertTrue(model.timelineIsOpen)
        XCTAssertEqual(model.speech.lead, "I opened your timeline.")
        // And it is handed back, because the user never asked for it.
        model.skip()
        XCTAssertEqual(world.timelineDismissals, 1)
    }

    /// The first defect, at the level the machine reads it. The beat asks for a gesture; only a
    /// gesture satisfies it, and no amount of time on the step does.
    func testTheDragBeatWaitsForARealGestureAndNotForTheClock() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .timeline)

        for _ in 0..<100 {
            world.clock += 3
            model.poll()
        }
        XCTAssertFalse(model.didDrag)
        XCTAssertFalse(model.gateIsSatisfied)
        XCTAssertFalse(model.advance(), "time passing is not a gesture")
        XCTAssertEqual(model.step, .timeline)
        XCTAssertEqual(
            model.speech.aside, "Swipe two fingers across your trackpad to travel through your day.")

        world.dragAcrossTheTimeline()
        XCTAssertTrue(model.didDrag)
        XCTAssertEqual(model.speech.lead, "There you go.", "and the line changes because the fact did")
        XCTAssertTrue(model.gateIsSatisfied)
        XCTAssertTrue(model.advance())
        XCTAssertEqual(model.step, .findMoments)
    }

    /// A timeline that never came up has nothing to drag, and the beat knows it rather than sitting
    /// the user out a wait that cannot end.
    func testADragBeatWithNoTimelineOffersTheWayOutAtOnce() {
        let world = World()
        world.screenGranted = true
        world.timelineCanOpen = false
        let model = makeModel(world)
        drive(model, world, to: .timeline)

        XCTAssertFalse(model.timelineIsOpen)
        XCTAssertTrue(model.waiverIsOffered)
        XCTAssertTrue(model.waive())
        XCTAssertEqual(model.step, .findMoments)
        XCTAssertFalse(model.didDrag, "and a waived beat is never recorded as a gesture")
    }

    func testAnOpenTimelineIsGivenTimeBeforeTheDragWayOutAppears() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .timeline)

        XCTAssertTrue(model.timelineIsOpen)
        XCTAssertFalse(model.waiverIsOffered)
        world.clock += TutorialModel.dragPatience + 1
        XCTAssertTrue(model.waiverIsOffered)
    }

    // MARK: - The handoff, which the tutorial performs

    /// The third defect. The tutorial opens Claude and puts the question in its prompt; it does not
    /// tell the user to go and ask something.
    func testTheHandoffAsksClaudeItselfAndSaysWhatReallyHappened() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .claudeHandoff)

        XCTAssertEqual(
            world.claudeAsks, [TutorialModel.suggestedQuestion],
            "the tutorial hands the question over rather than describing it")
        XCTAssertEqual(model.claudeAsk, .prompted(restarted: false, mayNotReachMe: false))
        XCTAssertEqual(model.speech.lead, "Your question is in Claude.")
        XCTAssertFalse(
            model.speech.everythingSaid.localizedCaseInsensitiveContains("ask claude"),
            "the card must not tell them to do the thing it just did: \(model.speech.everythingSaid)")
        XCTAssertEqual(
            world.claudeAsksRestartingFirst, [false],
            "nothing may agree to a restart on the user's behalf")
    }

    /// The beat may not quit an app the user is using without being asked. When a restart is
    /// genuinely needed the card says what it would cost and then waits — it hands nothing over
    /// until it is told to.
    func testAHandoffThatWouldCostARestartAsksFirst() {
        let world = World()
        world.screenGranted = true
        world.claudeNeedsRestart = true
        let model = makeModel(world)
        drive(model, world, to: .claudeHandoff)

        XCTAssertTrue(model.claudeNeedsRestart)
        XCTAssertTrue(world.claudeAsks.isEmpty, "the handoff must not run itself when it costs a quit")
        XCTAssertFalse(model.isAskingClaude)
        XCTAssertEqual(model.speech.lead, "Claude is open already.")
        XCTAssertTrue(
            model.speech.everythingSaid.contains("May I"),
            "the card has to ask: \(model.speech.everythingSaid)")

        model.askClaude(restartingFirst: true)
        XCTAssertEqual(world.claudeAsksRestartingFirst, [true])
    }

    /// A question the user has not answered is not a gate the user has met.
    ///
    /// The consent beat has exactly two ways forward and they are the two answers on the card.
    /// Continue was a third, and it answered nothing: pressing it handed Claude no question and then
    /// parked the user on a payoff beat whose gate only Claude can satisfy — an unwaivable wait for a
    /// tool call nobody had asked for.
    func testTheConsentBeatCannotBeWalkedPastWithoutAnswering() {
        let world = World()
        world.screenGranted = true
        world.claudeNeedsRestart = true
        let model = makeModel(world)
        drive(model, world, to: .claudeHandoff)

        XCTAssertEqual(model.speech.lead, "Claude is open already.", "the question is on screen")
        XCTAssertFalse(model.gateIsSatisfied, "an unanswered question is not a satisfied gate")
        XCTAssertFalse(
            model.advance(), "“continue” is not an answer to “may I close and reopen it?”")
        XCTAssertEqual(model.step, .claudeHandoff)
        XCTAssertTrue(world.claudeAsks.isEmpty, "and nothing was handed to Claude on the way past")

        // Nor is there a labelled way out: this beat is not waiting on the world, it is waiting on a
        // person, and both of the answers it will take are already on the card.
        XCTAssertFalse(model.waiverIsOffered)
        XCTAssertFalse(model.waive())
        world.clock += TutorialModel.framePatience + 1
        XCTAssertFalse(model.waiverIsOffered, "waiting longer does not answer it either")
        XCTAssertFalse(model.advance())
        XCTAssertEqual(model.step, .claudeHandoff)
    }

    /// Both answers are ways forward. The bug was never that the beat waited — it is that it could
    /// also be left without answering at all.
    func testEitherAnswerToTheConsentQuestionOpensTheWayForward() {
        for restartingFirst in [true, false] {
            let world = World()
            world.screenGranted = true
            world.claudeNeedsRestart = true
            let model = makeModel(world)
            drive(model, world, to: .claudeHandoff)

            model.askClaude(restartingFirst: restartingFirst)
            XCTAssertEqual(
                world.claudeAsks, [TutorialModel.suggestedQuestion],
                "answering “\(restartingFirst)” hands the question over")
            XCTAssertTrue(model.gateIsSatisfied, "an answered question is a way forward")
            XCTAssertTrue(model.advance())
            XCTAssertEqual(model.step, .claudeProof)
        }
    }

    /// Declining is a real choice, not a dead end: the question still goes over, and the card says
    /// the reach may be stale rather than quietly quitting their session to force the gate.
    func testDecliningTheRestartStillHandsTheQuestionOverAndSaysTheReachMayBeStale() {
        let world = World()
        world.screenGranted = true
        world.claudeNeedsRestart = true
        world.claudeAnswer = .prompted(restarted: false, mayNotReachMe: true)
        let model = makeModel(world)
        drive(model, world, to: .claudeHandoff)

        model.askClaude(restartingFirst: false)
        XCTAssertEqual(world.claudeAsksRestartingFirst, [false])
        XCTAssertEqual(model.claudeAsk, .prompted(restarted: false, mayNotReachMe: true))
        XCTAssertEqual(model.speech.lead, "Your question is in Claude.")
        XCTAssertFalse(
            model.speech.everythingSaid.contains("restarted it"),
            "a restart that did not happen must not be described: \(model.speech.everythingSaid)")

        XCTAssertTrue(model.advance())
        XCTAssertTrue(
            model.speech.everythingSaid.contains("quitting and reopening"),
            "a gate that may never fire has to name the way out: \(model.speech.everythingSaid)")
    }

    /// Every branch that did not fill a prompt says so, and the proof beat inherits the difference.
    func testAHandoffThatCouldNotFillThePromptNeverClaimsItDid() {
        for outcome in [TutorialClaudeAsk.copiedInstead, .notInstalled] {
            let world = World()
            world.screenGranted = true
            world.claudeAnswer = outcome
            let model = makeModel(world)
            // Stopped one beat short so the chime count below is about this handoff and not about
            // every earned gate before it.
            drive(model, world, to: .query)
            world.searchInTheRealPanel("captured", results: 1)
            let chimesBefore = world.chimes
            XCTAssertTrue(model.advance())
            XCTAssertEqual(model.step, .claudeHandoff)

            XCTAssertEqual(model.claudeAsk, outcome)
            XCTAssertFalse(
                model.speech.everythingSaid.contains("in the prompt"),
                "\(outcome) must not read as a pre-fill: \(model.speech.everythingSaid)")
            XCTAssertEqual(
                world.chimes, chimesBefore, "and it does not get the sound that means it worked")

            XCTAssertTrue(model.advance())
            XCTAssertEqual(model.step, .claudeProof)
            XCTAssertEqual(model.speech.lead, "Paste it into Claude.")
        }
    }

    /// A handoff still in flight is not a handoff that happened, and the card cannot be walked past
    /// while it is running.
    func testTheCardWaitsWhileClaudeIsStillBeingAsked() {
        let world = World()
        world.screenGranted = true
        world.claudeAnswer = nil  // the callback never comes back
        let model = makeModel(world)
        drive(model, world, to: .claudeHandoff)

        XCTAssertTrue(model.isAskingClaude)
        XCTAssertNil(model.claudeAsk, "“we asked” is not an outcome")
        XCTAssertEqual(model.speech.lead, "Let me ask Claude for you.")
        // The same rule as the consent question, one state later: the beat asked something and has
        // not been answered, so nothing may leave it. Asserted on the model rather than trusted to a
        // `.disabled` in the view, which is where it used to live alone.
        XCTAssertFalse(model.gateIsSatisfied)
        XCTAssertFalse(model.advance(), "a handoff still in flight cannot be walked past")
        XCTAssertEqual(model.step, .claudeHandoff)
    }

    /// **The bed has a last beat, and it is not "whenever the tutorial ends".**
    ///
    /// `Sound.music` is a 24-second loop. It used to be started at `begin()` and stopped only by
    /// teardown — and the tutorial does not end on a schedule: `claudeProof` waits on Claude calling
    /// one of our tools and cannot be waived, so a run that sits there loops the same bar at somebody
    /// for as long as they leave it open. Reported from that very beat: "you should really stop the
    /// noise after a while."
    ///
    /// What ends it is the first beat that hands the user to another application — see
    /// `TutorialStep.carriesTheBed`. Two claims, and the second is the one a naive fix gets wrong:
    /// it stops **once**, so the teardown that follows does not ask the audio layer for a second fade
    /// on a bed that has already gone.
    func testTheBedStopsWhenTheTutorialHandsTheUserToAnotherAppAndOnlyOnce() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)

        drive(model, world, to: .invitation)
        XCTAssertEqual(world.musicStarts, 1)
        XCTAssertEqual(world.musicStops, 0, "the opening card is the thing on screen; it keeps the bed")

        drive(model, world, to: .collectFrames)
        XCTAssertEqual(
            world.musicStops, 1,
            "the bed is still looping under the browser window this beat just opened")

        // The rest of the run, including a long stall on the beat only Claude can end.
        drive(model, world, to: .claudeProof)
        for _ in 0..<200 {
            world.clock += 6
            model.poll()
        }
        XCTAssertEqual(world.musicStops, 1, "something restarted or re-stopped the bed mid-run")
        XCTAssertEqual(world.musicStarts, 1)

        model.skip()
        XCTAssertEqual(
            world.musicStops, 1, "teardown asked for a second fade on a bed that had already gone")
    }

    /// Which beats hand the user somewhere that is not this app — named rather than derived, because
    /// the derivation is the production code's and a test that repeated it would pass however the
    /// rule happened to be wired.
    func testTheBedEndsAtTheFirstBeatThatHandsTheUserToAnotherApp() throws {
        // Ours, and the bed belongs over them.
        XCTAssertFalse(TutorialStep.invitation.handsOverToAnotherApp)
        XCTAssertFalse(TutorialStep.screenAccess.handsOverToAnotherApp)
        XCTAssertFalse(TutorialStep.timeline.handsOverToAnotherApp, "the timeline is our own window")
        XCTAssertFalse(TutorialStep.query.handsOverToAnotherApp)
        // Somebody else's: the browser, and Claude twice.
        XCTAssertTrue(TutorialStep.collectFrames.handsOverToAnotherApp)
        XCTAssertTrue(TutorialStep.claudeHandoff.handsOverToAnotherApp)
        XCTAssertTrue(TutorialStep.claudeProof.handsOverToAnotherApp)

        // The end therefore falls *inside* the run rather than at the end of it, which is the whole
        // point: the beat that can wait on Claude indefinitely must not be the one holding the bed.
        let flow = TutorialStep.flow
        let firstHandover = try XCTUnwrap(
            flow.firstIndex(where: \.handsOverToAnotherApp), "nothing ends the bed at all")
        XCTAssertLessThan(
            firstHandover, try XCTUnwrap(flow.firstIndex(of: .claudeProof)),
            "the bed outlasts every beat that is guaranteed to end")
    }

    func testEveryAdvanceClicksAndTheMusicRunsForExactlyOneRun() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        model.begin()
        XCTAssertEqual(world.musicStarts, 1)
        model.begin()  // idempotent
        XCTAssertEqual(world.musicStarts, 1)

        let clicksBefore = world.clicks
        stepForward(model, world)
        XCTAssertGreaterThan(world.clicks, clicksBefore, "every advance has its click")
    }

    // MARK: - The gate table itself

    /// A static tripwire on the honesty contract: the two gates that must never be waivable, asserted
    /// at the level the machine reads them.
    func testTheGatesThatCannotBeWaivedAreNotWaivable() {
        XCTAssertFalse(TutorialGate.realSearchResult.isWaivable)
        XCTAssertFalse(TutorialGate.genuineToolCall.isWaivable)
        XCTAssertTrue(TutorialGate.realFrames.isWaivable)
        XCTAssertTrue(TutorialGate.screenRecordingGrant.isWaivable)
        XCTAssertTrue(TutorialGate.realHotkey.isWaivable)
        XCTAssertTrue(TutorialGate.realGesture.isWaivable)
        // The panel is waivable and the *answer* is not, and the split is the point: a pill that
        // cannot be pressed is a machine problem the tutorial can work around by opening the panel
        // itself, while a search that found nothing is the one thing it may never work around.
        XCTAssertTrue(TutorialGate.realSearchPanel.isWaivable)
        XCTAssertEqual(TutorialStep.collectFrames.gate, .realFrames)
        XCTAssertEqual(TutorialStep.openActivity.gate, .realHotkey)
        XCTAssertEqual(TutorialStep.timeline.gate, .realGesture)
        XCTAssertEqual(TutorialStep.findMoments.gate, .realSearchPanel)
        XCTAssertEqual(TutorialStep.query.gate, .realSearchResult)
        XCTAssertEqual(TutorialStep.claudeProof.gate, .genuineToolCall)
    }

    /// Nothing is earned by starting. Every fact the flow's gates read is false on a model that has
    /// only ever been begun — the one thing a new gate must never be is true by default, because
    /// that is how a beat silently stops asking for anything at all.
    func testAFreshRunHasEarnedNothing() {
        let world = World()
        let model = makeModel(world)
        model.begin()
        model.poll()
        XCTAssertEqual(model.framesCollected, 0)
        XCTAssertFalse(model.screenIsGranted)
        XCTAssertFalse(model.hotkeyFired)
        XCTAssertFalse(model.timelineIsOpen)
        XCTAssertFalse(model.didDrag)
        XCTAssertFalse(model.searchPanelIsOpen)
        XCTAssertEqual(model.resultCount, 0)
        XCTAssertEqual(model.lastQuery, "")
        XCTAssertNil(model.openedMomentHasPicture)
        XCTAssertNil(model.claudeAsk)
        XCTAssertNil(model.proof)
        XCTAssertFalse(model.didOpenReadingMaterial)
        XCTAssertNil(model.claudeFrame)
    }

    func testEveryNonTerminalStepHasASuccessorAndTerminalsHaveNone() {
        for step in TutorialStep.flow {
            XCTAssertNotNil(step.next, "\(step) leads nowhere")
        }
        XCTAssertNil(TutorialStep.finished.next)
        XCTAssertNil(TutorialStep.skipped.next)
        XCTAssertEqual(TutorialStep.flow.last?.next, .finished)
    }

    /// Every step that asks the user to work somewhere else is a step that must not park itself in
    /// the middle of where they are working. Stated as a table so adding a beat that opens something
    /// has to come here and say where its card goes.
    func testOnlyTheBeatsThatAskForWorkElsewhereLeaveTheMiddle() {
        let expected: [TutorialStep: TutorialPlacement] = [
            .collectFrames: .outOfTheWay,
            .claudeHandoff: .clearOfClaude,
            .claudeProof: .clearOfClaude,
        ]
        for step in TutorialStep.flow {
            XCTAssertEqual(
                step.placement, expected[step] ?? .centred, "\(step) sits in the wrong place")
        }
    }

    // MARK: - The page the capture beat opens

    /// The beat opens one page, it is Anthropic's, and the card asks for the gesture that actually
    /// produces frames.
    ///
    /// The URL is asserted through the constant rather than by opening anything: a test that proved
    /// this by launching a browser would take over the screen of whoever ran the suite.
    ///
    /// The **path** is held as well as the host, and it is not decoration. This beat's gate is real
    /// frames, capture dedupes perceptually, and a short mostly-static page can be scrolled end to
    /// end while producing almost none — so "somewhere on anthropic.com" is not enough, it has to be
    /// a page there is something to scroll through. Reported as: "open anthropic's research page,
    /// maybe, because there's just more content to read and people can scroll through."
    func testTheCaptureBeatOpensAnthropicsSiteAndAsksForAScroll() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .collectFrames)

        XCTAssertEqual(world.pagesOpened, [TutorialModel.readingMaterial])
        XCTAssertEqual(TutorialModel.readingMaterial.host(), "www.anthropic.com")
        XCTAssertEqual(
            TutorialModel.readingMaterial.path(), "/research",
            "the home page has too little on it for the gesture this beat asks for to produce frames")
        XCTAssertTrue(model.didOpenReadingMaterial)

        let said = model.speech.everythingSaid
        XCTAssertTrue(said.contains("Anthropic"), "the card does not name the page it opened: \(said)")
        XCTAssertTrue(
            said.localizedCaseInsensitiveContains("scroll"),
            "the card asks for something other than the gesture that produces frames: \(said)")
    }

    /// One page for the whole run, and only this beat opens it. The tutorial is not a thing that
    /// opens windows on somebody's machine as it goes.
    func testNoOtherBeatOpensAnything() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        model.begin()
        var guardrail = 0
        while !model.step.isTerminal, guardrail < 40 {
            stepForward(model, world)
            guardrail += 1
        }
        XCTAssertEqual(world.pagesOpened, [TutorialModel.readingMaterial])
    }

    /// A page that would not open is not described as open.
    ///
    /// The same rule as every other claim in this flow: `NSWorkspace` answers, and the sentence
    /// follows the answer. A card pointing at a browser that never came up would send the user
    /// looking for a window that is not there.
    func testAPageThatWouldNotOpenIsNeverClaimedAsOpened() {
        let world = World()
        world.screenGranted = true
        world.pageWillOpen = false
        let model = makeModel(world)
        drive(model, world, to: .collectFrames)

        XCTAssertFalse(model.didOpenReadingMaterial)
        let said = model.speech.everythingSaid
        XCTAssertFalse(said.contains("Anthropic"), "the card claims a page it never opened: \(said)")
        XCTAssertTrue(
            said.localizedCaseInsensitiveContains("scroll"),
            "the fallback still has to ask for the gesture: \(said)")
    }

    /// **The beat asks for a gesture, not for attention.**
    ///
    /// "Go and look at something" asked the user to do a thing this app cannot observe, on content
    /// they had to find for themselves, on a machine that is brand new. Read off the production copy
    /// through the production model in every state the capture beat has, so the phrasing cannot come
    /// back on one branch.
    func testNoCardAsksTheUserToLookAtSomething() {
        var said: [String] = []

        for opens in [true, false] {
            let world = World()
            world.screenGranted = true
            world.pageWillOpen = opens
            let model = makeModel(world)
            drive(model, world, to: .collectFrames)
            said.append(model.speech.everythingSaid)
            // The state where frames have genuinely landed says something else again.
            world.frameCount = TutorialModel.frameTarget
            model.poll()
            said.append(model.speech.everythingSaid)
        }

        // And the branch where the screen was never granted at all, which is allowed to say the app
        // cannot see — that is a statement about this app, not an instruction to the user.
        let blind = World()
        let blindModel = makeModel(blind)
        drive(blindModel, blind, to: .screenAccess)
        blind.clock += TutorialModel.grantPatience + 1
        XCTAssertTrue(blindModel.waive())
        said.append(blindModel.speech.everythingSaid)
        XCTAssertTrue(
            blind.pagesOpened.isEmpty,
            "a page was opened for somebody who had just declined to be watched, and nothing they "
                + "scroll on it can be captured")

        XCTAssertEqual(said.count, 5)
        for line in said {
            for phrase in ["look at", "look around", "see anything", "watch something"] {
                XCTAssertFalse(
                    line.localizedCaseInsensitiveContains(phrase),
                    "“\(phrase)” is the beat asking for attention instead of a gesture: \(line)")
            }
        }
    }

    // MARK: - The chord, being typed

    /// **The chord this app actually teaches is not a double tap, and the card must not draw one.**
    ///
    /// This replaces `testTheDemonstratedTapIsOneCapAndIsTheGestureTheDetectorFires`, which replayed
    /// the `⌘⌘` cycle through `ModifierDoubleTap` — the production detector — and asserted that it
    /// fired. Both the detector and the double-tap shortcut are gone: `openActivity`'s default is
    /// `.bothCommandKeys`, and `openSearch`, the only action that was ever a double tap, was a
    /// second chord onto the same window. So the claim worth pinning moved. It is no longer "the
    /// drawing fires the detector" but "the drawing is the *other* shape entirely": `⌘ + ⌘` routes
    /// to `TutorialCommandPair`, which draws two caps pressed at once, and never to the repeated-tap
    /// cycle, which draws one cap struck twice. Those two pictures teach different gestures and only
    /// one of them opens the window.
    ///
    /// The expected value is taken from production — `GlobalShortcuts.Action.openActivity`'s own
    /// default chord — rather than from a literal here, so a chord that moves without this moving
    /// fails rather than passes.
    func testTheChordTheCardTeachesIsTheBothCommandGestureAndNotADoubleTap() {
        let chord = GlobalShortcuts.Action.openActivity.defaultChord.display

        XCTAssertTrue(
            TutorialCommandPair.matches(chord),
            "the card would fall through to the repeated-tap drawing for \(chord)")
        XCTAssertEqual(TutorialCommandPair.spoken, "Press both Command keys together")

        // …and the reading the report rejected — one key struck twice — is a different string and a
        // different drawing. `⌘⌘` is what a double tap prints, and it must not reach the pair.
        XCTAssertFalse(
            TutorialCommandPair.matches("⌘⌘"),
            "⌘⌘ is the double tap; drawing it as two keys at once is the reported defect in reverse")
        XCTAssertTrue(TutorialChordCycle(chord: "⌘⌘").isRepeatedTap)
    }


    /// The other double tap this app ships: `⌘⌘⇧`, a repeated ⌘ with Shift **held across both
    /// halves**. Collapsing the duplicate must not collapse the modifier with it, and the held cap
    /// must not blink in sympathy with the tapped one.
    func testADoubleTapWithAHeldModifierKeepsTheModifierDownThroughout() {
        let cycle = TutorialChordCycle(chord: "⌘⌘⇧")
        XCTAssertEqual(cycle.keys, ["⌘", "⇧"], "the held modifier is a cap; the repeat is not")
        XCTAssertTrue(cycle.isRepeatedTap)
        XCTAssertEqual(cycle.spoken, "Tap ⌘ twice while holding ⇧")

        var tappedGaps = 0
        for beat in 1..<cycle.beats {
            let tappedLifted = cycle.isDown(0, at: beat - 1) && !cycle.isDown(0, at: beat)
            if tappedLifted, cycle.isDown(0, at: (beat + 1) % cycle.beats) { tappedGaps += 1 }
            // Shift is down for every beat the tap is, and never lifts between the two halves.
            if cycle.isDown(0, at: beat) {
                XCTAssertTrue(cycle.isDown(1, at: beat), "⇧ let go mid-chord at beat \(beat)")
            }
        }
        XCTAssertEqual(tappedGaps, 1, "the tapped cap has to lift once, between the two strikes")
    }

    /// An ordinary chord is held together: the modifiers stay down while the last key is struck, and
    /// there is a moment where the whole chord is down — which is the moment it would fire.
    func testAnOrdinaryChordIsDrawnAsKeysHeldTogether() {
        let cycle = TutorialChordCycle(chord: "⌘⇧K")
        XCTAssertEqual(cycle.keys, ["⌘", "⇧", "K"])
        XCTAssertFalse(cycle.isRepeatedTap)

        var sawWholeChord = false
        for beat in 0..<cycle.beats {
            let down = (0..<3).map { cycle.isDown($0, at: beat) }
            // Nothing lifts before the key after it goes down: a cap that is down implies every cap
            // before it is down too.
            for index in 1..<3 where down[index] {
                XCTAssertTrue(
                    down[index - 1],
                    "cap \(index) is down at beat \(beat) with cap \(index - 1) already lifted")
            }
            if down.allSatisfy({ $0 }) { sawWholeChord = true }
        }
        XCTAssertTrue(sawWholeChord, "the chord is never shown complete, so it is never shown firing")
    }

    /// A keycap is a key, not a character: `Space` is one cap and not five, and the loop repeats
    /// rather than running off the end of a step that can last minutes.
    func testTheCycleSplitsByKeycapAndRepeatsForever() {
        XCTAssertEqual(TutorialChordCycle(chord: "⌘⇧Space").keys, ["⌘", "⇧", "Space"])
        // One cap and a count, not two caps — see `testTheDemonstratedTapIsOneCapAnd…`.
        XCTAssertEqual(TutorialChordCycle(chord: "⌥⌥").keys, ["⌥"])
        XCTAssertEqual(TutorialChordCycle(chord: "⌥⌥").taps, 2)
        XCTAssertEqual(TutorialChordCycle(chord: "F5").keys, ["F5"])
        XCTAssertEqual(TutorialChordCycle(chord: "F5").taps, 1, "an ordinary key is struck once")

        for chord in ["⌘⌘", "⌘⇧K", "F5"] {
            let cycle = TutorialChordCycle(chord: chord)
            XCTAssertGreaterThan(cycle.beats, 0)
            for beat in 0..<cycle.beats {
                for index in cycle.keys.indices {
                    XCTAssertEqual(
                        cycle.isDown(index, at: beat),
                        cycle.isDown(index, at: beat + cycle.beats),
                        "\(chord) does not repeat at cap \(index), beat \(beat)")
                }
            }
            // Every cap is up at some point, so the loop has a rest and reads as repeated rather
            // than as a stuck key.
            let restingBeat = (0..<cycle.beats).first { beat in
                cycle.keys.indices.allSatisfy { !cycle.isDown($0, at: beat) }
            }
            XCTAssertNotNil(restingBeat, "\(chord) never lets go")
        }
    }

    /// A chord this app could not parse still has to divide by something, and must not draw a key
    /// that is not there.
    func testAnEmptyChordDrawsNothingAndDoesNotDivideByZero() {
        let cycle = TutorialChordCycle(chord: "")
        XCTAssertTrue(cycle.keys.isEmpty)
        XCTAssertGreaterThan(cycle.beats, 0)
        for beat in 0..<24 {
            XCTAssertFalse(cycle.isDown(0, at: beat))
            XCTAssertFalse(cycle.isDown(-1, at: beat))
        }
    }

    // MARK: - Both Command keys, being pressed together

    /// **The gesture is recognised from the shortcut's spelling, and `⌘⌘` is not it.**
    ///
    /// The tutorial learns what to draw from one string — the printed shortcut it already shows the
    /// user — and the whole risk in that is the collision at the middle of this test. `⌘⌘`, two
    /// glyphs with nothing between them, has always meant the **repeated tap** in this product and
    /// still ships as half of the search default (`⌘⌘⇧`). The pair gesture is a different thing
    /// entirely — two physical keys, one modifier mask, no repeat — and if a picture of it ever
    /// captured `⌘⌘` the search beat would start teaching a gesture that cannot fire it.
    ///
    /// So the rule is a *separator*, not a spelling, and both halves of that are asserted: every
    /// plausible way the shortcut layer might punctuate the pair is accepted, and the adjacent form
    /// is refused along with everything that has a third key in it.
    func testTheLaunchGestureIsRecognisedFromItsSpellingAndNothingElse() {
        for spelling in ["⌘ + ⌘", "⌘+⌘", "⌘ ⌘", "⌘·⌘", "⌘-⌘", "⌘ & ⌘", " ⌘  +  ⌘ "] {
            XCTAssertTrue(
                TutorialCommandPair.matches(spelling),
                "“\(spelling)” is two Command keys and a joiner, and the card would draw a chord")
        }

        for other in ["⌘⌘", "⌘⌘⇧", "⌘ + ⌘ + ⌘", "⌘ + ⌥", "⌘ + K", "⌘⇧K", "⌘", "F5", ""] {
            XCTAssertFalse(
                TutorialCommandPair.matches(other),
                "“\(other)” was taken for both Command keys pressed together")
        }

        // The reason the adjacent form has to stay out, stated where the exclusion is: it is already
        // spoken for, by the drawing that got it right.
        XCTAssertTrue(
            TutorialChordCycle(chord: "⌘⌘").isRepeatedTap,
            "⌘⌘ stopped meaning a repeated tap, so the separator rule is now guarding nothing")
    }

    /// **Neither Command key is ever drawn going down without the other.**
    ///
    /// The whole of the defect this gesture's picture exists to avoid, as an assertion over every
    /// beat of the loop rather than over the one frame somebody happened to look at. The report was
    /// *"expressing both the command keys one by one. It's supposed to be both the command keys
    /// together"* — a drawing that lights one cap and then the other is not a slower version of this
    /// gesture, it is a different gesture, and a pose type that could express it would let it back
    /// in the next time the timing is retuned.
    func testNeitherCommandKeyIsEverShownGoingDownWithoutTheOther() {
        for reduceMotion in [false, true] {
            // Negative ticks included: the counter wraps with `&+`, and a modulo that went negative
            // would index the loop off its own front.
            for tick in -TutorialCommandPair.beats..<(TutorialCommandPair.beats * 3) {
                let pose = TutorialCommandPair.pose(at: tick, reduceMotion: reduceMotion)
                XCTAssertEqual(
                    pose.leftIsDown, pose.rightIsDown,
                    "one Command key is down alone at tick \(tick) (reduce motion: \(reduceMotion))")
                XCTAssertEqual(
                    pose.tie, pose.bothAreDown ? 1 : 0,
                    "the tie disagrees with the keys it is tying at tick \(tick)")
            }
        }

        // …and the loop is a loop: it presses, it lets go, and it repeats. Without the rest beats
        // the caps read as merely highlighted and nothing is ever seen to be *pressed*.
        let ticks = 0..<TutorialCommandPair.beats
        XCTAssertTrue(ticks.contains { TutorialCommandPair.pose(at: $0, reduceMotion: false).bothAreDown })
        XCTAssertTrue(ticks.contains { !TutorialCommandPair.pose(at: $0, reduceMotion: false).bothAreDown })
        for tick in ticks {
            XCTAssertEqual(
                TutorialCommandPair.pose(at: tick, reduceMotion: false),
                TutorialCommandPair.pose(at: tick + TutorialCommandPair.beats, reduceMotion: false),
                "the loop does not repeat at tick \(tick)")
        }
    }

    /// **Reduce Motion holds the pair down instead of letting it go**, which is the opposite of what
    /// the chord demonstration does under the same setting — and the difference is the point.
    ///
    /// A chord at rest is still legible: the caps say which keys. A *pair* at rest is two identical
    /// ⌘ caps sitting there, which is precisely the ambiguous picture the moving version was built
    /// to replace. So the still frame is the gesture at the instant it fires, and it does not depend
    /// on where in the loop the setting happened to be turned on.
    func testReduceMotionHoldsTheCommandPairAtTheMomentItFires() {
        for tick in 0..<(TutorialCommandPair.beats * 2) {
            let pose = TutorialCommandPair.pose(at: tick, reduceMotion: true)
            XCTAssertTrue(pose.bothAreDown, "the still frame lets go at tick \(tick)")
            XCTAssertEqual(pose.tie, 1, "the still frame's tie is half drawn at tick \(tick)")
        }

        // Which is only a *choice* if the moving version does something else, so: it lets go.
        XCTAssertTrue(
            (0..<TutorialCommandPair.beats).contains {
                !TutorialCommandPair.pose(at: $0, reduceMotion: false).bothAreDown
            },
            "the loop never releases, so holding it down under Reduce Motion decides nothing")
    }

    /// The row is a keyboard's bottom row, and the two keys the beat is about are on opposite sides
    /// of the one landmark everybody can find without looking down.
    ///
    /// "The two either side of the space bar" is what the card says out loud, so the drawing has to
    /// be arranged that way — and the tie is positioned from these same numbers, which is why they
    /// are asserted rather than eyeballed.
    func testTheKeyboardRowPutsOneCommandKeyEitherSideOfTheSpaceBar() {
        let caps = TutorialCommandRow.caps
        let commands = TutorialCommandRow.commandIndices
        XCTAssertEqual(commands.count, 2, "a pair is two keys")
        XCTAssertEqual(commands.first, TutorialCommandRow.leftCommand)
        XCTAssertEqual(commands.last, TutorialCommandRow.rightCommand)

        XCTAssertEqual(caps[TutorialCommandRow.leftCommand].label, "⌘")
        XCTAssertEqual(caps[TutorialCommandRow.rightCommand].label, "⌘")
        XCTAssertEqual(
            caps[TutorialCommandRow.leftCommand].width, caps[TutorialCommandRow.rightCommand].width,
            "one Command key drawn wider than the other reads as the more important of the two")

        // Exactly one cap stands between them, it carries no legend, and it is the widest thing on
        // the row: that is a space bar and nothing else on a keyboard is.
        let between = (TutorialCommandRow.leftCommand + 1)..<TutorialCommandRow.rightCommand
        XCTAssertEqual(between.count, 1, "the two Command caps are not either side of one key")
        let spaceBar = caps[between.lowerBound]
        XCTAssertEqual(spaceBar.label, "")
        XCTAssertEqual(spaceBar.width, caps.map(\.width).max())

        // The tie's endpoints, which are cap centres in the row's own coordinates.
        let leftCentre = TutorialCommandRow.centre(of: TutorialCommandRow.leftCommand)
        let rightCentre = TutorialCommandRow.centre(of: TutorialCommandRow.rightCommand)
        XCTAssertLessThan(leftCentre, rightCentre)
        XCTAssertGreaterThan(leftCentre, 0)
        XCTAssertLessThan(rightCentre, TutorialCommandRow.width)
        XCTAssertEqual(
            TutorialCommandRow.width,
            caps.reduce(0) { $0 + $1.width } + TutorialCommandRow.gap * CGFloat(caps.count - 1),
            accuracy: 0.001)
        // An index the row does not have must not fall off the front of it — the tie would be drawn
        // from x = 0, which is a stroke leaving the board.
        XCTAssertEqual(TutorialCommandRow.centre(of: caps.count + 4), 0)

        // And it has to stand *beside* a sentence on a fixed-width card, not instead of one. A row
        // that grew past this would push "opens it from anywhere." onto a second line, or off.
        let cardContent = TutorialOverlay.width - TutorialCardView.horizontalPadding * 2
        XCTAssertLessThan(
            TutorialCommandRow.width, cardContent * 0.6,
            "the keyboard row has taken the width the card's own sentence needs")
    }

    /// **The card's sentence and the card's drawing describe the same gesture**, and the beat picks
    /// both from the one thing it knows about the shortcut: how it is printed.
    func testTheOpenActivityBeatSaysTheGestureItDraws() {
        let pair = World()
        pair.screenGranted = true
        pair.chord = "⌘ + ⌘"
        let pairModel = makeModel(pair)
        drive(pairModel, pair, to: .openActivity)

        XCTAssertTrue(pairModel.activityChordIsCommandPair)
        // And it names the window the chord actually opens. "Open your timeline." was the line until
        // ⌘ + ⌘ stopped opening one, and a card teaching a gesture towards the wrong window is the
        // single worst thing this beat can do.
        XCTAssertEqual(pairModel.speech.lead, "Open your activity.")
        XCTAssertEqual(
            pairModel.speech.aside,
            "Press both Command keys together — the two either side of the space bar.")
        // The same words the animation is labelled with, which is what stops a screen reader and a
        // pair of eyes being told two different things.
        XCTAssertEqual(
            pairModel.speech.aside?.hasPrefix(TutorialCommandPair.spoken), true,
            "the card's sentence and the drawing's label have drifted apart")

        // A rebind, or any machine still on the typed default, gets the chip that types itself and
        // the sentence that goes with it.
        let typed = World()
        typed.screenGranted = true
        typed.chord = "⌘⇧K"
        let typedModel = makeModel(typed)
        drive(typedModel, typed, to: .openActivity)

        XCTAssertFalse(typedModel.activityChordIsCommandPair)
        XCTAssertEqual(typedModel.speech.lead, "Open your activity.")
        XCTAssertEqual(typedModel.speech.aside, "Press these keys, and it will come up.")
    }

    // MARK: - The gesture, being made

    /// **The content moves with the fingers, by exactly as much.**
    ///
    /// The one thing the drag demonstration can get *wrong* rather than merely ugly: a picture whose
    /// panels travelled against the hand would teach an inverted drag to somebody who has never made
    /// this gesture, and it would look perfectly deliberate.
    func testTheDemonstratedPanelsFollowTheHandExactly() {
        for step in stride(from: -1.0, through: 1.0, by: 0.1) {
            let phase = CGFloat(step)
            XCTAssertEqual(
                TutorialScrollCycle.content(phase), TutorialScrollCycle.hand(phase), accuracy: 0.001,
                "the panels disagree with the hand at phase \(phase)")
        }
        XCTAssertEqual(TutorialScrollCycle.hand(0), 0, "the sweep has to have a resting middle")
        XCTAssertEqual(TutorialScrollCycle.hand(1), TutorialScrollCycle.travel)
        XCTAssertEqual(TutorialScrollCycle.hand(-1), -TutorialScrollCycle.travel)
    }

    /// The sweep runs both ways, because which direction travels *back* through the day depends on
    /// the user's own natural-scrolling setting and the gate accepts either.
    func testTheSweepTravelsBothWays() {
        XCTAssertLessThan(TutorialScrollCycle.hand(-1), 0)
        XCTAssertGreaterThan(TutorialScrollCycle.hand(1), 0)
    }

    /// The ticks behind the panels travel the same way and less far. Parallax, not disagreement: a
    /// backdrop moving the other way would be a second inverted drag in the same picture.
    func testTheBackdropTrailsTheHandWithoutContradictingIt() {
        for step in stride(from: -1.0, through: 1.0, by: 0.1) {
            let phase = CGFloat(step)
            let hand = TutorialScrollCycle.hand(phase)
            let backdrop = TutorialScrollCycle.backdrop(phase)
            XCTAssertGreaterThanOrEqual(hand * backdrop, 0, "the backdrop travels against the hand")
            XCTAssertLessThanOrEqual(abs(backdrop), abs(hand))
        }
        XCTAssertNotEqual(TutorialScrollCycle.backdrop(1), TutorialScrollCycle.hand(1))
    }

    /// **The fingers are on the glass for the whole travelling part of the sweep, and lift only
    /// where it has stopped.**
    ///
    /// The lift is what makes the drawing a *swipe* rather than two dots sliding — a gesture has a
    /// beginning and an end, and the picture that got reported had neither. But a lift is also the
    /// one thing that can put this demonstration back in disagreement with itself: the panels follow
    /// the fingertips exactly (`testTheDemonstratedPanelsFollowTheHandExactly`), so any travel that
    /// happens while the fingers are off the glass is content moving with nothing pushing it.
    ///
    /// The sweep is eased, so it has all but stopped at its ends, and that is the property this
    /// pins: whatever the thresholds are retuned to, the distance covered during the lift has to
    /// stay too small to read as movement. Eight points is about a third of one panel.
    func testTheFingersStayOnTheGlassForTheWholeTravellingPartOfTheSweep() {
        XCTAssertEqual(TutorialScrollCycle.contact(0), 1, "the middle of a swipe is not a hover")
        XCTAssertEqual(TutorialScrollCycle.contact(1), 0, "the fingers never come off")
        XCTAssertEqual(TutorialScrollCycle.contact(-1), 0, "the fingers only come off at one end")

        var previous = 1.0
        for step in stride(from: 0.0, through: 1.0, by: 0.02) {
            let phase = CGFloat(step)
            let contact = TutorialScrollCycle.contact(phase)
            XCTAssertLessThanOrEqual(
                contact, previous, "the fingers press back down mid-lift at phase \(phase)")
            XCTAssertEqual(
                contact, TutorialScrollCycle.contact(-phase), accuracy: 0.001,
                "the fingers behave differently at the two ends of a sweep that runs both ways")
            previous = contact
        }

        let travelledWhileLifting =
            abs(TutorialScrollCycle.hand(1))
            - abs(TutorialScrollCycle.hand(TutorialScrollCycle.plantedBelow))
        XCTAssertLessThanOrEqual(
            travelledWhileLifting, 8,
            "the panels travel \(travelledWhileLifting) pt with the fingers off the glass, which is "
                + "content moving on its own")
    }

    /// **The fingertips land on the pad, and the fingers leave it by the near edge.**
    ///
    /// The one part of this drawing that is arithmetic rather than judgement, and the one part that
    /// failed silently while it was being written: a finger is laid out as a tall box with its tip at
    /// the top, SwiftUI centres that box in the trackpad, and centring puts the tip half a finger
    /// *above* the far edge — outside the clip, drawing nothing. Nothing about that is visible in the
    /// source and nothing about it is visible in a still frame of an empty pad either. It is visible
    /// here.
    func testTheFingertipsLandInsideTheTrackpadAndTheFingersRunOffTheNearEdge() {
        let halfHeight = TutorialScrollCycle.trackpadHeight / 2
        // Where the tip ends up in the trackpad's own coordinates, centre at 0, far edge negative.
        let tip = TutorialScrollCycle.fingerOffset - TutorialScrollCycle.fingerLength / 2
        XCTAssertEqual(tip, TutorialScrollCycle.padDrop - halfHeight, accuracy: 0.001)

        XCTAssertGreaterThan(tip, -halfHeight, "the fingertips are drawn off the far edge, and clipped")
        XCTAssertLessThan(
            tip + TutorialScrollCycle.padHeight, halfHeight,
            "the contact patches hang off the near edge, so the thing that reads as the fingers "
                + "touching the glass is the thing that gets cut")
        XCTAssertGreaterThan(
            tip + TutorialScrollCycle.fingerLength, halfHeight,
            "the fingers end inside the pad, which draws two stubs rather than a hand")

        // Two, and legibly two: patches closer together than they are wide read as one smudge.
        XCTAssertGreaterThan(TutorialScrollCycle.padSpread, TutorialScrollCycle.padWidth)

        // And the pair stays on the glass at the ends of its travel — a finger that sweeps off the
        // side of the trackpad is a gesture the trackpad could not have received.
        let outermost =
            TutorialScrollCycle.travel + TutorialScrollCycle.padSpread / 2
            + TutorialScrollCycle.padWidth / 2
        XCTAssertLessThan(
            outermost, TutorialScrollCycle.trackpadWidth / 2,
            "the sweep carries the fingers over the edge of the pad they are supposed to be on")
    }

    /// **Reduce Motion parks the sweep, so the sweep's meaning has to be drawn instead.**
    ///
    /// A parked version of this picture is two fingers resting on a trackpad, which is a drawing of
    /// *not* doing the thing the card is asking for. So the still frame grows the one thing the
    /// moving one does not need — a double-headed arrow across the pad — and the pose is where that
    /// substitution is decided, because a view is not a place a claim can be tested.
    func testReduceMotionParksTheSweepAndDrawsItsDirectionInstead() {
        for step in stride(from: -1.0, through: 1.0, by: 0.25) {
            let still = TutorialSweepPose(phase: CGFloat(step), reduceMotion: true)
            XCTAssertEqual(still.fingers, 0, "the still frame moved at phase \(step)")
            XCTAssertEqual(still.content, 0)
            XCTAssertEqual(still.backdrop, 0)
            XCTAssertEqual(still.contact, 1, "a half-lifted finger in a still frame is a smudge")
            XCTAssertTrue(still.showsTravelArrow, "nothing is moving and nothing says which way")
        }

        // The moving version says it by moving, and must not wear the glyph as well.
        let moving = TutorialSweepPose(phase: 0.8, reduceMotion: false)
        XCTAssertFalse(moving.showsTravelArrow)
        XCTAssertEqual(moving.fingers, TutorialScrollCycle.hand(0.8), accuracy: 0.001)
        XCTAssertEqual(moving.content, moving.fingers, accuracy: 0.001)
        XCTAssertNotEqual(moving.fingers, 0)
    }

    // MARK: - Standing clear of Claude

    /// The two Claude beats are the only ones that ask where Claude's window is, and they stop
    /// asking the moment the flow leaves them.
    func testClaudesWindowIsOnlyLookedForByTheBeatsThatStandBesideIt() {
        let world = World()
        world.screenGranted = true
        world.claudeWindow = CGRect(x: 400, y: 200, width: 900, height: 700)
        let model = makeModel(world)

        drive(model, world, to: .collectFrames)
        model.poll()
        XCTAssertNil(model.claudeFrame, "a beat with no Claude on it read Claude's window")
        XCTAssertEqual(world.claudeWindowLookups, 0)

        drive(model, world, to: .claudeHandoff)
        model.poll()
        XCTAssertEqual(model.claudeFrame, world.claudeWindow)
        XCTAssertGreaterThan(world.claudeWindowLookups, 0)

        drive(model, world, to: .allSet)
        model.poll()
        XCTAssertNil(model.claudeFrame, "the frame outlived the beat that needed it")
    }

    /// **The card stands beside Claude rather than on it.**
    ///
    /// The report was one sentence — the flow window blocks the Claude window — and the fix has to
    /// hold on geometry the machine it was written on does not have, so it is swept here rather than
    /// looked at once.
    func testTheCardParksInTheWidestBandBesideClaude() {
        let visible = NSRect(x: 0, y: 0, width: 1_800, height: 1_000)
        let card = NSSize(width: 470, height: 300)
        let margin: CGFloat = 28

        // Claude on the left: the card takes the room on the right.
        let onTheLeft = CGRect(x: 40, y: 100, width: 900, height: 800)
        let right = TutorialOverlay.parked(card, in: visible, clearOf: onTheLeft, margin: margin)
        XCTAssertFalse(right.intersects(onTheLeft), "the card is on top of Claude")
        XCTAssertGreaterThanOrEqual(right.minX, onTheLeft.maxX)

        // Claude on the right: the card takes the room on the left.
        let onTheRight = CGRect(x: 860, y: 100, width: 900, height: 800)
        let left = TutorialOverlay.parked(card, in: visible, clearOf: onTheRight, margin: margin)
        XCTAssertFalse(left.intersects(onTheRight))
        XCTAssertLessThanOrEqual(left.maxX, onTheRight.minX)

        // Both bands fit: the wider one wins, so the card is never squeezed into a sliver it barely
        // clears when there is a whole half-display next door.
        let slightlyLeft = CGRect(x: 520, y: 100, width: 700, height: 800)
        let widest = TutorialOverlay.parked(card, in: visible, clearOf: slightlyLeft, margin: margin)
        XCTAssertGreaterThanOrEqual(widest.minX, slightlyLeft.maxX)
    }

    /// A Claude that spans the display still leaves the card off the composer at the foot of it.
    func testAFullWidthClaudePushesTheCardAboveIt() {
        let visible = NSRect(x: 0, y: 0, width: 1_400, height: 1_200)
        let card = NSSize(width: 470, height: 260)
        let wide = CGRect(x: 20, y: 0, width: 1_360, height: 860)

        let parked = TutorialOverlay.parked(card, in: visible, clearOf: wide, margin: 28)
        XCTAssertFalse(parked.intersects(wide), "the card is over the conversation")
        XCTAssertGreaterThanOrEqual(parked.minY, wide.maxY)
    }

    /// A Claude that covers the whole usable area leaves nothing clear. The card then takes the top
    /// trailing corner — over Claude, but off the column its answer arrives in and nowhere near the
    /// composer, which is the keystroke the next beat is waiting for.
    func testACardWithNowhereClearToStandStaysOffTheComposer() {
        let visible = NSRect(x: 0, y: 0, width: 1_200, height: 800)
        let card = NSSize(width: 470, height: 300)
        let fullScreen = visible

        let parked = TutorialOverlay.parked(card, in: visible, clearOf: fullScreen, margin: 28)
        XCTAssertGreaterThan(
            parked.minY, visible.midY, "the card is in the bottom half, over the composer")
        XCTAssertGreaterThan(
            parked.minX, visible.midX, "the card is over the middle, where the answer arrives")
        XCTAssertTrue(visible.contains(parked), "the card left the usable area")
    }

    /// Claude not found is not a licence to sit in the middle: the middle is exactly where an app
    /// that has just been opened puts its window.
    func testAClaudeThatCannotBeFoundStillKeepsTheCardOutOfTheMiddle() {
        let visible = NSRect(x: 0, y: 0, width: 1_600, height: 900)
        let card = NSSize(width: 470, height: 300)

        let parked = TutorialOverlay.parked(card, in: visible, clearOf: nil, margin: 28)
        XCTAssertGreaterThan(parked.minX, visible.midX)
        XCTAssertTrue(visible.contains(parked))
    }

    // MARK: - The card's own surface

    /// **The card's surface is the app's one glass object, so its highlight is cut by its corner.**
    ///
    /// One look at the capture beat produced two complaints — "above it, there's a weird line showing
    /// up" and "I can see like weird like boxy edges and it's not completely rounded" — and they were
    /// one defect. The card wore `.inkGlassPanel()`, which cuts the material and the scrim with a
    /// `.clipShape` and then hangs the specular top edge on as an `.overlay` **outside** that cut. A
    /// 1 pt white line then runs the card's full width at its very top, straight past both corners as
    /// the panel curves away from it, which squares the card off.
    ///
    /// Behavioural rather than a source scrape: the production card is hosted for real and the AppKit
    /// tree it produces is walked. The old path is not merely a different spelling of the same thing
    /// — it puts *no* `InkGlassView` in that tree at all, so this fails on it, and for the right
    /// reason. The claims after that are the ones that make the corner correct, asserted on the real
    /// view the card ended up with rather than on the type it was built from.
    ///
    /// A tree walk cannot see the old sheen directly and that is worth writing down: SwiftUI draws a
    /// `Color` straight into its parent's layer without making an `NSView` for it, so "find the white
    /// line and check what clips it" is not a question at this level. What can be asked is which
    /// object the card's surface *is* — and `InkGlassView` puts the sheen inside the masked panel by
    /// construction, which is the thing being relied on.
    @MainActor
    func testTheCardsSurfaceIsTheAppsGlassSoItsHighlightIsCutByTheCorner() throws {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        model.begin()

        // Hosted the way `TutorialOverlay` hosts it — a plain container with the hosting view inside
        // it, never as a borderless window's `contentView`, which re-enters AppKit's window-sizing
        // negotiation and crashes.
        let size = NSSize(width: TutorialOverlay.width, height: 300)
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: size), styleMask: [.borderless],
            backing: .buffered, defer: false)
        let container = NSView(frame: NSRect(origin: .zero, size: size))
        window.contentView = container
        let hosting = NSHostingView(
            rootView: TutorialCardView(model: model, chrome: TutorialOverlayChrome()))
        hosting.frame = NSRect(origin: .zero, size: size)
        container.addSubview(hosting)
        hosting.layoutSubtreeIfNeeded()

        let found = hosting.descendants(of: InkGlassView.self)
        XCTAssertEqual(
            found.count, 1,
            "the card's surface is not the app's one glass, so nothing here can say what cuts it")
        let glass = try XCTUnwrap(found.first)

        // The corner is real: masked *and* rounded. A layer that rounds without masking rounds only
        // its own background, which is how a rounded scrim ends up under a square everything-else.
        XCTAssertTrue(
            glass.panel.layer?.masksToBounds == true, "the panel does not clip its own contents")
        XCTAssertEqual(glass.panel.layer?.cornerRadius, InkGlass.cornerRadius)

        // And the two things drawn *on* the glass are inside it, which is what the corner then cuts.
        // The sheen is the one that was wrong: outside the panel it is a hairline drawn over the
        // card, and inside it, it is light caught on the card's face.
        XCTAssertTrue(
            glass.sheen.isDescendant(of: glass.panel),
            "the specular top edge is drawn outside the corner and runs off both ends of it")
        XCTAssertTrue(glass.material.isDescendant(of: glass.panel))
    }

    /// **The proof beat never takes the keyboard.** It is waiting for Claude to call one of our
    /// tools, which happens when the user presses Return in Claude's composer — and an accessory app
    /// that activates over Claude eats exactly that keystroke.
    func testTheProofBeatNeverTakesTheKeyboardOffClaude() {
        XCTAssertFalse(TutorialStep.claudeProof.takesFocusOnEntry)
        // The handoff still does: its two answers are buttons on the card, and Claude is opened by
        // this beat afterwards rather than being typed into during it.
        XCTAssertTrue(TutorialStep.claudeHandoff.takesFocusOnEntry)
        // A coach mark leaves focus where the user is working. The query beat used to be the
        // exception because it carried its own text field; the typing happens in the real search bar
        // now, which is a non-activating panel holding the first responder while this app is not
        // frontmost — a card that activated over it would take the field away at the exact moment it
        // is asking somebody to type into it.
        XCTAssertFalse(TutorialStep.timeline.takesFocusOnEntry)
        XCTAssertFalse(TutorialStep.findMoments.takesFocusOnEntry)
        XCTAssertFalse(TutorialStep.query.takesFocusOnEntry)
        XCTAssertTrue(TutorialStep.invitation.takesFocusOnEntry)
    }

    // MARK: - The search beats are coach marks, not a search surface

    /// **The two search beats point at the real panel and stand clear of it.**
    ///
    /// This is the layout half of the same fix. The pill beat hangs its card under the "Search All"
    /// pill; the query beat's card targets the panel and is placed under its foot, because the
    /// panel's field is its top edge and that is the part of it the user is being asked to type into.
    ///
    /// And exactly two beats *use* the panel, which is what makes `TutorialModel.enter` closing it on
    /// the way into every other one a complete rule rather than a list of named transitions — the
    /// drag beat included, which is where the panel the chord opened is taken away.
    func testTheSearchBeatsPointAtTheSurfaceTheyAreCoaching() {
        XCTAssertEqual(TutorialStep.findMoments.target, .searchAllButton)
        XCTAssertEqual(TutorialStep.query.target, .searchPanel)
        XCTAssertTrue(TutorialStep.findMoments.usesSearchPanel)
        XCTAssertTrue(TutorialStep.query.usesSearchPanel)

        // …and nothing else in the flow does, so no other beat can quietly inherit a panel — or a
        // coach mark pointing at a surface it is not about.
        for step in TutorialStep.allCases where step != .findMoments && step != .query {
            XCTAssertFalse(
                step.usesSearchPanel, "\(step) would carry the panel into a beat about something else")
            XCTAssertNotEqual(step.target, .searchPanel, "\(step)")
            XCTAssertNotEqual(step.target, .searchAllButton, "\(step)")
        }
    }

    /// The panel is ours and the music is not somebody else's problem: the search beats happen in
    /// **this** app, so they must not be mistaken for the handovers that stop the cinematic bed.
    func testTheSearchBeatsAreNotAHandoffToAnotherApp() {
        XCTAssertFalse(TutorialStep.findMoments.handsOverToAnotherApp)
        XCTAssertFalse(TutorialStep.query.handsOverToAnotherApp)
    }

    /// **A card under the real search panel, measured against the panel's own placement.**
    ///
    /// The card used to draw a two-across grid of screenshots and this test used to hold that grid
    /// under a ceiling derived from the search surface's own maximum. Neither is a claim about this
    /// card any more — the results are `SearchResultsView`'s — but the argument survives inverted:
    /// the coach mark has to stand *beside* the panel, and the one thing it may never be laid over is
    /// the field at the top of it.
    ///
    /// **The rectangle comes from `SearchBarWindow`'s own placement helper and never from
    /// `SearchLayout` arithmetic.** An earlier version of this test reassembled the surface's
    /// geometry out of layout constants — a width, a content ceiling, a tenth of the display — and
    /// that was wrong in the way a test cannot notice: it went on passing against a shape the app had
    /// stopped opening at. In production the coach mark reads the panel's *live* frame
    /// (`SearchBarWindow.panelFrame`, through `TutorialTargetLocator`), which no headless test can
    /// produce; the nearest honest stand-in is to ask the same type where it puts the surface. That
    /// helper is the seam between this test and `Search/**`: if it is renamed, this asks for the new
    /// name rather than doing the arithmetic itself.
    ///
    /// Measured on two real displays: the one the card comfortably clears, and the one where it
    /// cannot and degrades instead.
    @MainActor
    func testTheQueryCardStandsUnderTheSearchPanelAndNeverOverItsField() {
        XCTAssertTrue(InkTestFonts.registered, "the bundled faces have to be registered to measure type")

        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        // Every state the card can be in while the panel is up. Which is tallest is not obvious, so
        // all of them are measured rather than the one that looks worst.
        var tallest = cardHeight(model)
        world.searchInTheRealPanel("throughput", results: 12)
        tallest = max(tallest, cardHeight(model))
        world.searchInTheRealPanel("zzzz", results: 0)
        tallest = max(tallest, cardHeight(model))
        let card = NSSize(width: TutorialOverlay.width, height: tallest)

        // Where the app really puts the panel: horizontally centred, its top an easy tenth of the way
        // down, clamped into the display. Asked of `SearchBarWindow` rather than reproduced here.
        func panel(in visible: NSRect) -> NSRect { SearchBarWindow.defaultFrame(in: visible) }

        // A 16" MacBook's usable area. The card clears the panel outright here.
        let large = NSRect(x: 0, y: 0, width: 1728, height: 1092)
        let onLarge = TutorialOverlay.under(card, panel: panel(in: large), in: large, margin: 14)
        XCTAssertFalse(
            onLarge.intersects(panel(in: large)),
            "the card overlaps the search panel on a 16\" display, where there is room for it not to")
        XCTAssertTrue(large.contains(onLarge))

        // A 13" MacBook's, where the panel leaves less room under it than this card needs. It has to
        // degrade over the *foot* of the panel — a scrolling grid — and never over its head.
        let small = NSRect(x: 0, y: 0, width: 1470, height: 931)
        let onSmall = TutorialOverlay.under(card, panel: panel(in: small), in: small, margin: 14)
        XCTAssertTrue(small.contains(onSmall), "the card must stay on the display whatever it overlaps")
        XCTAssertLessThan(
            onSmall.maxY, panel(in: small).midY,
            "the card has risen past the middle of the panel — the field, the query chip and the "
                + "↵ Ask Claude affordance are the top of that surface and are what this beat is asking "
                + "the user to touch")
    }

    /// The card's ideal height at the width the overlay hosts it at — the same `fittingSize` read
    /// `TutorialOverlay.fittingHeight()` sizes the window from, so this measures what ships.
    @MainActor
    private func cardHeight(_ model: TutorialModel) -> CGFloat {
        let host = NSHostingView(
            rootView: TutorialCardView(model: model, chrome: TutorialOverlayChrome()))
        host.layoutSubtreeIfNeeded()
        return host.fittingSize.height
    }
}

// MARK: - Walking the rendered tree

/// Enough of a view walk for the card's surface to be asserted on the thing that reaches the screen
/// rather than on the source that built it.
extension NSView {
    /// Every view of `type` beneath this one, self excluded.
    fileprivate func descendants<T: NSView>(of type: T.Type) -> [T] {
        var found: [T] = []
        for view in subviews {
            if let match = view as? T { found.append(match) }
            found.append(contentsOf: view.descendants(of: type))
        }
        return found
    }
}
