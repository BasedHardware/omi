import ContextCore
import XCTest

@testable import ContextApp

/// The tutorial's step machine, tested where the product's credibility actually sits: that nothing it
/// claims can be produced by time passing, by an empty search, or by this app alone — and that
/// leaving it, from any step, takes everything it put on screen back off.
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
        var timelineIsVisible = true
        var momentNear: TutorialMoment?

        var articleOpens = true
        var openedArticles: [URL] = []
        var clipboard: [String] = []
        var restartedClaude = 0

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
            environment.openArticle = { url in
                self.openedArticles.append(url)
                return self.articleOpens
            }
            environment.copyToClipboard = { self.clipboard.append($0) }
            environment.restartClaude = {
                self.restartedClaude += 1
                return true
            }
            environment.presentTimeline = { self.timelinePresentations += 1 }
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
    }

    private func makeModel(_ world: World) -> TutorialModel {
        TutorialModel(environment: world.environment())
    }

    private func memory(_ text: String = "LINGsCARS car leasing", at: Double = 1_699_999_000)
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
        case .realSearchResult:
            world.searchResults = [memory()]
            // Advances by itself, and only because there was something to find.
            model.search("leasing")
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
                .invitation, .article, .collectFrames, .openTimeline, .timeline, .scrollBack,
                .findMoments, .query, .foundIt, .claudeHandoff, .claudeProof, .allSet, .menuBar,
                .finished,
            ],
            "the tutorial's order is the lesson; a reordering has to be deliberate")
        XCTAssertEqual(model.step, .finished)
    }

    /// G3 is asked for "at the right moment", which includes not asking at all.
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

    func testTheProgressDotsCountThisRunsPlan() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        model.begin()
        XCTAssertEqual(model.progress.total, TutorialStep.flow.count - 1)
        XCTAssertEqual(model.progress.index, 0)
        stepForward(model, world)
        XCTAssertEqual(model.progress.index, 1)
    }

    // MARK: - G2

    func testTheArticleIsOpenedInTheDefaultBrowserAndFailureIsAdmitted() {
        let world = World()
        world.screenGranted = true
        world.articleOpens = false
        let model = makeModel(world)
        drive(model, world, to: .article)

        XCTAssertEqual(world.openedArticles, [TutorialModel.articleURL])
        XCTAssertEqual(model.articleDidOpen, false, "a browser that did not open must not be claimed")
        // Over https and nothing else asserted about the host: the page is a product decision that can
        // change, and a test that pins it would be a test of the copy rather than of the step.
        XCTAssertEqual(TutorialModel.articleURL.scheme, "https")
        XCTAssertNotNil(TutorialModel.articleURL.host())
    }

    // MARK: - G5, the counter

    /// The whole of G5. A frame count that could be satisfied by waiting would make every other
    /// number this app reports suspect.
    func testTheFrameCounterReflectsTheStoreAndNeverElapsedTime() {
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

        // Frames genuinely land.
        world.frameCount = TutorialModel.frameTarget
        model.poll()
        XCTAssertEqual(model.framesCollected, TutorialModel.frameTarget)
        XCTAssertTrue(model.advance())
        XCTAssertEqual(model.step, .openTimeline)
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

        drive(model, world, to: .allSet)
        XCTAssertTrue(
            model.framesSummary.contains("No frames arrived"),
            "a waived step must not be reported as a success: \(model.framesSummary)")
    }

    func testAWaivedFrameStepNeverClaimsFramesLanded() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .collectFrames)
        world.frameCount = 2
        model.poll()
        world.clock += TutorialModel.framePatience + 1
        XCTAssertTrue(model.waive())
        XCTAssertTrue(model.framesSummary.contains("Only 2 frames"), model.framesSummary)
        XCTAssertFalse(model.framesSummary.contains("searchable"))
    }

    // MARK: - G10/G12, the search

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
        XCTAssertFalse(model.advance(), "the found-it beat is not reachable by pressing continue")
        XCTAssertFalse(model.step.gate.isWaivable, "and it cannot be waived either")
    }

    func testARealResultCarriesTheRealHitIntoTheFoundItBeat() {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .query)

        let hit = memory("cheap car leasing, no hidden fees", at: 1_699_998_888)
        world.searchResults = [hit]
        model.search("leasing")

        XCTAssertEqual(model.step, .foundIt)
        XCTAssertEqual(model.results, [hit])
        XCTAssertEqual(model.lastQuery, "leasing")
    }

    func testTappingAMemoryGoesBackToThatExactMoment() throws {
        let world = World()
        world.screenGranted = true
        world.momentNear = TutorialMoment(
            at: 1_699_998_890, app: "Safari", windowTitle: "LINGsCARS car leasing",
            imagePath: "/tmp/does-not-need-to-exist.heic")
        let model = makeModel(world)
        drive(model, world, to: .foundIt)

        // `XCTUnwrap` rather than a force unwrap: this file is also run against deliberately broken
        // builds to check that these assertions bite, and a crash there would abort the whole suite
        // before the other honesty tests got to report.
        let hit = try XCTUnwrap(model.results.first)
        model.choose(hit)
        XCTAssertEqual(model.chosenMemory, hit)
        XCTAssertEqual(model.chosenMoment, world.momentNear)
        XCTAssertEqual(world.scrubs, [hit.at], "the timeline is repositioned on the real instant")
    }

    /// G9 advances because the real control in the real window was pressed.
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
        XCTAssertFalse(model.advance())
        XCTAssertEqual(model.step, .claudeProof)
        XCTAssertFalse(model.step.gate.isWaivable, "and there is no button that can stand in for it")

        // Claude really calls a tool.
        recordStamp(world, tool: "screen", at: world.clock + 1)
        model.poll()
        XCTAssertEqual(model.proof?.tool, "screen")
        XCTAssertTrue(model.advance())
        XCTAssertEqual(model.step, .allSet)
    }

    func testTheHandoffCopiesTheQuestionAndSnapshotsBeforeTellingAnyoneToRestart() throws {
        let world = World()
        world.screenGranted = true
        let model = makeModel(world)
        drive(model, world, to: .claudeHandoff)

        // A call served *before* the handoff, i.e. before the user was told to restart Claude.
        recordStamp(world, tool: "recall", at: world.clock - 1)
        model.handOffToClaude()
        XCTAssertEqual(world.clipboard, [TutorialModel.suggestedQuestion])
        XCTAssertEqual(world.restartedClaude, 1)

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
        XCTAssertEqual(world.spotlightShows, 1, "G14 rings the real status item")

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
        drive(model, world, to: .scrollBack)
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
        world.timelineIsVisible = false
        let model = makeModel(world)
        drive(model, world, to: .timeline)
        XCTAssertEqual(world.timelinePresentations, 1)
        XCTAssertFalse(model.timelineIsOpen, "a window that did not appear must not be described")

        let second = World()
        second.screenGranted = true
        let openModel = makeModel(second)
        drive(openModel, second, to: .timeline)
        XCTAssertTrue(openModel.timelineIsOpen)
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
        XCTAssertEqual(TutorialStep.collectFrames.gate, .realFrames)
        XCTAssertEqual(TutorialStep.query.gate, .realSearchResult)
        XCTAssertEqual(TutorialStep.claudeProof.gate, .genuineToolCall)
    }

    func testEveryNonTerminalStepHasASuccessorAndTerminalsHaveNone() {
        for step in TutorialStep.flow {
            XCTAssertNotNil(step.next, "\(step) leads nowhere")
        }
        XCTAssertNil(TutorialStep.finished.next)
        XCTAssertNil(TutorialStep.skipped.next)
        XCTAssertEqual(TutorialStep.flow.last?.next, .finished)
    }
}
