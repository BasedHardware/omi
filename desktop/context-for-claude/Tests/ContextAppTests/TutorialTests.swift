import ContextCore
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
        var searchResults: [TutorialMemory] = []
        var stampURL: URL?
        /// Starts closed. Nothing in this app opens a timeline until something opens it, and a world
        /// that begins with one already up would let a beat read a window it never caused.
        var timelineIsVisible = false
        var momentNear: TutorialMoment?

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

        /// Whether the machine is genuinely listening for the timeline chord.
        var chordIsArmed = true
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
        var scrubs: [Double] = []

        /// The two watchers, as the model armed them. Held rather than counted so a test can fire
        /// the *real* callback — which is the only way anything sets the gates they feed.
        var hotkeyWatch: (() -> Void)?
        var dragWatch: (() -> Void)?

        func environment() -> TutorialEnvironment {
            var environment = TutorialEnvironment()
            environment.pollInterval = nil
            environment.now = { self.clock }
            environment.frameCount = { since in
                self.framesAskedSince.append(since)
                return self.frameCount
            }
            environment.search = { _ in self.searchResults }
            environment.frameNear = { _ in self.momentNear }
            environment.storeIsReadable = { true }
            environment.screenIsGranted = { self.screenGranted }
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
            environment.timelineChord = { "⌘⌘" }
            environment.timelineChordIsArmed = { self.chordIsArmed }
            environment.watchForTimelineHotkey = { self.hotkeyWatch = $0 }
            environment.stopWatchingTimelineHotkey = { self.hotkeyWatch = nil }
            environment.watchForDrag = { self.dragWatch = $0 }
            environment.stopWatchingDrag = { self.dragWatch = nil }
            environment.presentTimeline = {
                self.timelinePresentations += 1
                self.timelineIsVisible = self.timelineCanOpen
            }
            environment.dismissTimeline = { self.timelineDismissals += 1 }
            environment.timelineIsVisible = { self.timelineIsVisible }
            environment.scrubTimeline = { self.scrubs.append($0) }
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
        /// is what opens the window, and *then* to the tutorial's observer. Nothing here reaches
        /// into the model to set a flag — the only route in is the callback the model itself armed,
        /// which is what makes this beat's gate a fact about the user.
        func pressTimelineChord() {
            guard let fired = hotkeyWatch else { return }
            if timelineCanOpen {
                timelinePresentations += 1
                timelineIsVisible = true
            }
            fired()
        }

        /// The user really drags, far enough for `TutorialDrag` to call it a gesture.
        func dragAcrossTheTimeline() {
            dragWatch?()
        }
    }

    private func makeModel(_ world: World) -> TutorialModel {
        TutorialModel(environment: world.environment())
    }

    private func memory(_ text: String = "a line of captured text", at: Double = 1_699_999_000)
        -> TutorialMemory
    {
        TutorialMemory(at: at, when: "earlier", text: text, app: "Safari", kind: "screen")
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
            world.pressTimelineChord()
        case .realGesture:
            world.dragAcrossTheTimeline()
            model.advance()
        case .realSearchResult:
            world.searchResults = [memory()]
            // The search only fills the gate. Leaving the step is still the button's job, and the
            // button still checks.
            model.search("captured")
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
                .invitation, .collectFrames, .openTimeline, .timeline, .findMoments, .query,
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
        XCTAssertEqual(model.step, .openTimeline)
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
        XCTAssertEqual(waiting.lead, "I opened Anthropic's website.")
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
        XCTAssertEqual(model.step, .openTimeline)
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
                // The empty-handed line as well as the found-it one.
                world.searchResults = []
                model.search("nothing captured matches this")
                said.append(model.speech.everythingSaid)
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
        drive(unarmedModel, unarmed, to: .openTimeline)
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

    // MARK: - The search

    func testAnEmptySearchStaysOnTheStepAndSaysSo() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        world.searchResults = []
        model.search("something nobody captured")
        XCTAssertEqual(model.step, .query, "no result, no “found it”")
        XCTAssertNotNil(model.searchMessage)
        XCTAssertTrue(model.results.isEmpty)
        XCTAssertFalse(model.gateIsSatisfied)
        // The expected line is the user's own instruction for this beat, quoted in
        // `TutorialModel.speech`: "dont say search a word off the screen, say search something you
        // just looked at." What is under test is unchanged — an empty result leaves the mark on the
        // asking line rather than the found-it one.
        XCTAssertEqual(
            model.speech.lead, "Type something you just looked at.",
            "and the mark does not say it found one")
        XCTAssertFalse(model.advance(), "the found-it line is not reachable by pressing continue")
        XCTAssertFalse(model.step.gate.isWaivable, "and it cannot be waived either")
    }

    func testARealResultTurnsTheCardIntoTheFoundItBeatAndCarriesTheRealHit() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        let hit = memory("the invoice I was reading", at: 1_699_998_888)
        world.searchResults = [hit]
        model.search("invoice")

        XCTAssertEqual(model.step, .query, "the found-it beat is the same card, changed")
        XCTAssertEqual(model.results, [hit])
        XCTAssertEqual(model.lastQuery, "invoice")
        XCTAssertEqual(model.speech.lead, "There it is.")
        XCTAssertTrue(model.gateIsSatisfied)
        XCTAssertTrue(model.advance())
    }

    /// A second search that finds nothing takes the found-it line back off the card. The line is a
    /// statement about the current results, not a badge the step earned once.
    func testAFailedSecondSearchWithdrawsTheFoundItLine() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        world.searchResults = [memory()]
        model.search("captured")
        XCTAssertEqual(model.speech.lead, "There it is.")

        world.searchResults = []
        model.search("nothing at all")
        XCTAssertEqual(model.speech.lead, "Type something you just looked at.")
        XCTAssertNil(model.chosenMemory, "and the moment it was showing goes with it")
        XCTAssertFalse(model.gateIsSatisfied)
        XCTAssertFalse(model.advance())
    }

    func testTappingAMemoryGoesBackToThatExactMoment() throws {
        let world = World()
        world.screenGranted = true
        world.momentNear = TutorialMoment(
            at: 1_699_998_890, app: "Safari", windowTitle: "a captured window",
            imagePath: "/tmp/does-not-need-to-exist.heic")
        let model = makeModel(world)
        drive(model, world, to: .query)
        world.searchResults = [memory()]
        model.search("captured")

        // `XCTUnwrap` rather than a force unwrap: this file is also run against deliberately broken
        // builds to check that these assertions bite, and a crash there would abort the whole suite
        // before the other honesty tests got to report.
        let hit = try XCTUnwrap(model.results.first)
        model.choose(hit)
        XCTAssertEqual(model.chosenMemory, hit)
        XCTAssertEqual(model.chosenMoment, world.momentNear)
        XCTAssertEqual(world.scrubs, [hit.at], "the timeline is repositioned on the real instant")
        XCTAssertEqual(model.speech.aside, "That is the moment, exactly as it was.")
    }

    /// A hit with no surviving picture is said out loud rather than shown as a blank frame.
    func testAMomentWithNoPictureIsAdmitted() throws {
        let world = World()
        world.screenGranted = true
        world.momentNear = nil
        let model = makeModel(world)
        drive(model, world, to: .query)
        world.searchResults = [memory()]
        model.search("captured")

        let hit = try XCTUnwrap(model.results.first)
        model.choose(hit)
        XCTAssertNil(model.chosenMoment)
        XCTAssertEqual(
            model.speech.aside, "No picture survived that second — the words are what I still have.")
    }

    /// The pill advances because the real control in the real window was pressed.
    func testTheSearchPillOnlyAdvancesTheStepThatAskedForIt() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .findMoments)
        model.searchPillWasPressed()
        XCTAssertEqual(model.step, .query)

        // Pressing it again later must not skip anything.
        model.searchPillWasPressed()
        XCTAssertEqual(model.step, .query)
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
        XCTAssertEqual(openModel.speech.lead, "Everything I have seen.")
    }

    // MARK: - The chord, which the user has to press

    /// The whole of the second defect this beat exists to fix. The window used to open on its own
    /// the moment the step began, which taught nothing: the tutorial announced a shortcut and then
    /// did the shortcut's job. Now the step waits, and the only thing that satisfies it is the real
    /// shortcut layer delivering — the same delivery that opens the window.
    func testTheChordBeatWaitsForTheRealShortcutAndOpensNothingItself() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .openTimeline)

        // Five minutes of ticking on the step.
        for _ in 0..<100 {
            world.clock += 3
            model.poll()
        }
        XCTAssertEqual(
            world.timelinePresentations, 0,
            "the tutorial must not open the window it is asking the user to open")
        XCTAssertFalse(model.hotkeyFired)
        XCTAssertFalse(model.gateIsSatisfied)
        XCTAssertFalse(model.advance(), "no keypress, no advance")
        XCTAssertEqual(model.step, .openTimeline)

        // The user presses it. The shell's handler opens the window; the observer reports it.
        world.pressTimelineChord()
        XCTAssertTrue(model.hotkeyFired)
        XCTAssertEqual(model.step, .timeline, "the keypress is the transition")
        XCTAssertTrue(model.timelineIsOpen)
        XCTAssertFalse(model.didWaiveHotkey)
        XCTAssertEqual(model.speech.lead, "Everything I have seen.")
    }

    /// The honest way forward when the chord cannot fire at all: offered immediately, labelled with
    /// what did not happen, and the card owns up to having opened the window itself.
    func testAChordThatCannotFireOffersTheWayOutAtOnceAndSaysWhoOpenedIt() {
        let world = World()
        world.screenGranted = true
        world.chordIsArmed = false
        let model = makeModel(world)
        drive(model, world, to: .openTimeline)

        XCTAssertTrue(model.waiverIsOffered, "a chord nothing is listening for is not a slow start")
        XCTAssertEqual(model.speech.lead, "I cannot listen for that shortcut.")
        XCTAssertTrue(model.waive())

        XCTAssertEqual(model.step, .timeline)
        XCTAssertTrue(model.didWaiveHotkey)
        XCTAssertEqual(world.timelinePresentations, 1, "the fallback is the only thing that opens it")
        XCTAssertEqual(
            model.speech.lead, "I opened it for you.",
            "a window the tutorial opened must not be reported as the user's keypress")
    }

    /// An armed chord gets the full wait before the escape hatch appears — otherwise the way out is
    /// on screen before anyone has had a chance to press anything.
    func testAnArmedChordIsGivenTimeBeforeTheWayOutAppears() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .openTimeline)

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
        drive(model, world, to: .openTimeline)
        XCTAssertNotNil(world.hotkeyWatch, "the step that needs it arms it")

        world.pressTimelineChord()
        XCTAssertNil(world.hotkeyWatch, "and leaving the step takes it back down")

        model.skip()
        XCTAssertNil(world.dragWatch, "teardown stops every watcher")
    }

    // MARK: - The drag, which the user has to make

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
        XCTAssertEqual(model.speech.aside, "Drag across it with two fingers to travel through your day.")

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
            world.searchResults = [memory()]
            model.search("captured")
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
        XCTAssertEqual(TutorialStep.collectFrames.gate, .realFrames)
        XCTAssertEqual(TutorialStep.openTimeline.gate, .realHotkey)
        XCTAssertEqual(TutorialStep.timeline.gate, .realGesture)
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
        XCTAssertTrue(model.results.isEmpty)
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
    func testTheCaptureBeatOpensAnthropicsSiteAndAsksForAScroll() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .collectFrames)

        XCTAssertEqual(world.pagesOpened, [TutorialModel.readingMaterial])
        XCTAssertEqual(TutorialModel.readingMaterial.host(), "www.anthropic.com")
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

    /// **A double tap is drawn as a double tap.**
    ///
    /// `⌘⌘` is the app's own default for `openTimeline`, and it is one key struck twice. The two caps
    /// therefore never light together — a picture of two ⌘ keys held at once is a gesture no hand can
    /// make, and a user copying it would never fire the shortcut.
    func testARepeatedTapIsDrawnAsTwoSeparatePresses() {
        let cycle = TutorialChordCycle(chord: "⌘⌘")
        XCTAssertEqual(cycle.keys, ["⌘", "⌘"])
        XCTAssertTrue(cycle.isRepeatedTap)

        var beatsWithFirstDown: [Int] = []
        var beatsWithSecondDown: [Int] = []
        for beat in 0..<cycle.beats {
            let first = cycle.isDown(0, at: beat)
            let second = cycle.isDown(1, at: beat)
            XCTAssertFalse(first && second, "both caps are down at beat \(beat), which is not a tap")
            if first { beatsWithFirstDown.append(beat) }
            if second { beatsWithSecondDown.append(beat) }
        }

        XCTAssertFalse(beatsWithFirstDown.isEmpty, "the first tap never happens")
        XCTAssertFalse(beatsWithSecondDown.isEmpty, "the second tap never happens")
        XCTAssertLessThan(
            beatsWithFirstDown.last!, beatsWithSecondDown.first!,
            "the second tap has to follow the first, not precede it")
        XCTAssertGreaterThan(
            beatsWithSecondDown.first! - beatsWithFirstDown.last!, 1,
            "there is no gap between the taps, so they read as one long press")
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
        XCTAssertEqual(TutorialChordCycle(chord: "⌥⌥").keys, ["⌥", "⌥"])
        XCTAssertEqual(TutorialChordCycle(chord: "F5").keys, ["F5"])

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

    /// **The proof beat never takes the keyboard.** It is waiting for Claude to call one of our
    /// tools, which happens when the user presses Return in Claude's composer — and an accessory app
    /// that activates over Claude eats exactly that keystroke.
    func testTheProofBeatNeverTakesTheKeyboardOffClaude() {
        XCTAssertFalse(TutorialStep.claudeProof.takesFocusOnEntry)
        // The handoff still does: its two answers are buttons on the card, and Claude is opened by
        // this beat afterwards rather than being typed into during it.
        XCTAssertTrue(TutorialStep.claudeHandoff.takesFocusOnEntry)
        // A coach mark leaves focus where the user is working; the query beat is the exception,
        // because it has a text field the user has to type into.
        XCTAssertFalse(TutorialStep.timeline.takesFocusOnEntry)
        XCTAssertFalse(TutorialStep.findMoments.takesFocusOnEntry)
        XCTAssertTrue(TutorialStep.query.takesFocusOnEntry)
        XCTAssertTrue(TutorialStep.invitation.takesFocusOnEntry)
    }
}
