import ContextCore
import XCTest
@testable import ContextApp

/// The first-run cinematic's state machine.
///
/// The testable part is the *sequence*: which beat follows which, that Esc and "Skip intro" from
/// any beat land in exactly one terminal state, that Reduce Motion collapses every beat, that a
/// store with no frames still produces a valid beat 5, and that the run-once gate holds. Visual
/// fidelity is not asserted here — it is verified by building the bundle and looking at it, which
/// is what the commit messages record.
///
/// The director runs through two seams so none of this needs a window, a clock or an audio device:
/// an injected `sleep` (instant) and a recording `CinematicCues`.
private final class RecordingCues: CinematicCues {
    enum Event: Equatable {
        case prepare
        case musicStarted
        case musicStopped(fadeOut: TimeInterval)
        case effect(SoundEffect)
        case musicEnabled(Bool)
    }

    var events: [Event] = []
    private var musicOn = true

    func prepare() { events.append(.prepare) }
    func startMusic() { events.append(.musicStarted) }
    func stopMusic(fadeOut: TimeInterval) { events.append(.musicStopped(fadeOut: fadeOut)) }
    func play(_ effect: SoundEffect) { events.append(.effect(effect)) }

    var isMusicEnabled: Bool { musicOn }

    func setMusicEnabled(_ enabled: Bool) {
        musicOn = enabled
        events.append(.musicEnabled(enabled))
    }

    var effects: [SoundEffect] {
        events.compactMap { if case .effect(let effect) = $0 { return effect } else { return nil } }
    }

    var fadeOuts: [TimeInterval] {
        events.compactMap {
            if case .musicStopped(let fade) = $0 { return fade } else { return nil }
        }
    }
}

final class CinematicTests: XCTestCase {

    // MARK: - Fixtures

    /// Instant, so the whole sequence runs inside one test without a clock. Yields so the beat loop
    /// actually suspends and the `@Published` writes interleave the way they do in production.
    private static let instantSleep: CinematicDirector.Sleep = { _ in await Task.yield() }

    private static func frame(id: Int64, at seconds: Double, app: String = "Xcode") -> RewindFrame {
        RewindFrame(
            id: id,
            capturedAt: seconds,
            appName: app,
            bundleId: "com.example.\(app)",
            windowTitle: nil,
            ocrText: nil,
            imagePath: "/tmp/context-cinematic-tests/\(id).heic")
    }

    @MainActor
    private func makeDirector(
        timing: CinematicTiming = .standard,
        frames: CinematicFrameSource = StaticCinematicFrames(frames: [])
    ) -> (CinematicDirector, RecordingCues) {
        let cues = RecordingCues()
        let director = CinematicDirector(
            timing: timing,
            cues: cues,
            frames: frames,
            sleep: Self.instantSleep)
        return (director, cues)
    }

    /// Runs the director to its terminal state, or fails.
    @MainActor
    private func runToEnd(_ director: CinematicDirector) async throws -> CinematicEnd {
        var end: CinematicEnd?
        director.start { end = $0 }
        try await waitUntil { end != nil }
        return try XCTUnwrap(end)
    }

    /// Spins the main actor until `condition` holds. Bounded by iteration count, not by wall clock,
    /// so it cannot flake on a loaded machine.
    @MainActor
    private func waitUntil(_ condition: () -> Bool, iterations: Int = 20_000) async throws {
        for _ in 0..<iterations {
            if condition() { return }
            await Task.yield()
        }
        XCTFail("condition never held")
    }

    // MARK: - Beat order

    func testBeatsRunInSpecOrder() {
        XCTAssertEqual(
            CinematicBeat.allCases,
            [.dim, .mark, .bar, .prompt, .windows, .recede],
            "the six beats are the spec's six beats, in the spec's order")
    }

    func testSequenceWalksEveryBeatThenCompletes() {
        var sequence = CinematicSequence()
        XCTAssertEqual(sequence.stage, .idle)

        var walked: [CinematicBeat] = []
        while let beat = sequence.advance() { walked.append(beat) }

        XCTAssertEqual(walked, CinematicBeat.allCases)
        XCTAssertEqual(sequence.visited, CinematicBeat.allCases)
        XCTAssertEqual(sequence.stage, .ended(.completed))
    }

    func testAdvancingAFinishedSequenceIsANoOp() {
        var sequence = CinematicSequence()
        while sequence.advance() != nil {}
        XCTAssertEqual(sequence.stage, .ended(.completed))

        XCTAssertNil(sequence.advance())
        XCTAssertEqual(sequence.stage, .ended(.completed), "a late timer cannot walk a finished run")
        XCTAssertEqual(sequence.visited, CinematicBeat.allCases)
    }

    @MainActor
    func testDirectorVisitsEveryBeatInOrder() async throws {
        let (director, _) = makeDirector()
        let end = try await runToEnd(director)

        XCTAssertEqual(end, .completed)
        XCTAssertEqual(director.visitedBeats, CinematicBeat.allCases)
        XCTAssertTrue(director.stage.isTerminal)
    }

    // MARK: - Abort

    func testAbortFromEveryBeatIsTerminalAndRecordsThatBeat() {
        for beat in CinematicBeat.allCases {
            var sequence = CinematicSequence()
            while sequence.stage.beat != beat {
                XCTAssertNotNil(sequence.advance(), "could not reach \(beat.name)")
            }

            XCTAssertEqual(sequence.abort(), .skipped(beat))
            XCTAssertEqual(sequence.stage, .ended(.skipped(beat)))
            XCTAssertTrue(sequence.stage.isTerminal)
        }
    }

    func testAbortBeforeTheFirstBeatStillEnds() {
        var sequence = CinematicSequence()
        XCTAssertEqual(sequence.abort(), .skipped(.dim))
        XCTAssertTrue(sequence.stage.isTerminal)
    }

    func testAbortIsIdempotentAndNeverOverwritesTheFirstEnd() {
        var sequence = CinematicSequence()
        sequence.advance()  // dim
        XCTAssertEqual(sequence.abort(), .skipped(.dim))
        XCTAssertNil(sequence.abort(), "a second Esc has nothing left to end")
        XCTAssertNil(sequence.expire(), "the watchdog cannot overwrite a user's abort")
        XCTAssertEqual(sequence.stage, .ended(.skipped(.dim)))
    }

    @MainActor
    func testSkipHandsOffExactlyOnceAndFadesTheMusic() async throws {
        let (director, cues) = makeDirector()

        var handoffs: [CinematicEnd] = []
        director.start { handoffs.append($0) }
        // The instant clock means the run may already have finished; skip on top of it either way.
        director.skip()
        director.skip()

        try await waitUntil { !handoffs.isEmpty }
        XCTAssertEqual(handoffs.count, 1, "Esc, the button and the last beat share one exit")
        XCTAssertEqual(cues.fadeOuts.count, 1)
        XCTAssertGreaterThan(
            try XCTUnwrap(cues.fadeOuts.first), 0,
            "aborting fades the bed out; it never cuts it")
    }

    @MainActor
    func testCompletedRunFadesLongerThanAnAbortedOne() {
        XCTAssertGreaterThan(
            CinematicDirector.completedFadeOut,
            CinematicDirector.interruptedFadeOut,
            "a finished intro dissolves into the card; an aborted one stops")
        XCTAssertGreaterThan(CinematicDirector.interruptedFadeOut, 0, "never a cut")
    }

    func testEveryEndIsTerminalAndHandsOff() {
        let ends: [CinematicEnd] = [.completed, .skipped(.prompt), .expired(.windows)]
        for end in ends {
            XCTAssertTrue(CinematicStage.ended(end).isTerminal)
        }
        XCTAssertFalse(CinematicEnd.completed.wasInterrupted)
        XCTAssertTrue(CinematicEnd.skipped(.mark).wasInterrupted)
        XCTAssertTrue(CinematicEnd.expired(.mark).wasInterrupted)
    }

    // MARK: - Sound

    func testEveryBeatHasACue() {
        for beat in CinematicBeat.allCases {
            // Exhaustive by construction — this fails to compile if a beat is ever added without a
            // cue, and fails here if one is ever mapped to nothing.
            let effect = CinematicCue.effect(for: beat)
            XCTAssertTrue(SoundEffect.allCases.contains(effect), "\(beat.name) has no cue")
        }
    }

    func testTheStretchIsTheSwoosh() {
        XCTAssertEqual(
            CinematicCue.effect(for: .prompt), .swoosh,
            "the spec puts the swoosh on the stretch")
        XCTAssertEqual(
            CinematicCue.effect(for: .windows), .swoosh,
            "and one per card as the swarm arrives")
    }

    @MainActor
    func testMusicStartsOnTheFirstBeatAndStopsExactlyOnce() async throws {
        let (director, cues) = makeDirector()
        _ = try await runToEnd(director)

        let starts = cues.events.filter { $0 == .musicStarted }
        XCTAssertEqual(starts.count, 1, "the bed is started by beat 1 and by nothing else")
        XCTAssertEqual(cues.fadeOuts.count, 1, "and stopped once, on the way out")
        XCTAssertEqual(cues.events.first, .prepare, "decoders are warmed before the first cue")
    }

    @MainActor
    func testOneSwooshPerCard() async throws {
        let frames = (0..<12).map { Self.frame(id: Int64($0), at: 1_000 + Double($0) * 30) }
        let (director, cues) = makeDirector(frames: StaticCinematicFrames(frames: frames))
        _ = try await runToEnd(director)

        XCTAssertEqual(
            cues.effects.filter { $0 == .swoosh }.count,
            1 + director.cards.count,
            "the stretch, plus one swoosh per card that flew in")
    }

    @MainActor
    func testMuteControlPersistsThroughTheDirector() {
        let (director, cues) = makeDirector()
        XCTAssertTrue(director.musicEnabled)

        director.toggleMusic()
        XCTAssertFalse(director.musicEnabled)
        XCTAssertEqual(cues.events.last, .musicEnabled(false))

        director.toggleMusic()
        XCTAssertTrue(director.musicEnabled)
    }

    // MARK: - Reduce Motion

    func testReducedTimingCollapsesEveryBeatToOneCrossFade() {
        let reduced = CinematicTiming.reduced
        for beat in CinematicBeat.allCases {
            XCTAssertEqual(
                reduced.duration(of: beat), CinematicTiming.crossFade, accuracy: 0.0001,
                "\(beat.name) must be a cross-fade under Reduce Motion")
        }
        XCTAssertTrue(reduced.isCrossFade)
        XCTAssertEqual(reduced.typing, 0, "the question arrives whole rather than typing itself")
        XCTAssertEqual(reduced.cardStagger, 0, "the swarm arrives together rather than in sequence")
    }

    func testReducedTimingIsShorterThanStandardAndStandardStillHoldsOnTheMark() {
        XCTAssertLessThan(CinematicTiming.reduced.total, CinematicTiming.standard.total)
        XCTAssertEqual(
            CinematicTiming.reduced.total,
            CinematicTiming.crossFade * Double(CinematicBeat.allCases.count),
            accuracy: 0.0001)

        let standard = CinematicTiming.standard
        XCTAssertEqual(
            standard.mark,
            standard.head + standard.eyes + standard.legs + standard.markHold + standard.wordmark,
            accuracy: 0.0001,
            "beat 2's sub-beats have to add up to beat 2")
        XCTAssertEqual(
            standard.prompt,
            standard.stretch + standard.typing + standard.promptHold,
            accuracy: 0.0001)
        XCTAssertEqual(
            standard.mark, CinematicBeat.allCases.map(standard.duration(of:)).max(),
            "the mark is the longest beat: it is where the app introduces itself")
    }

    @MainActor
    func testReduceMotionStillPlaysEveryBeatWithItsSound() async throws {
        let (director, cues) = makeDirector(timing: .reduced)
        let end = try await runToEnd(director)

        XCTAssertEqual(end, .completed)
        XCTAssertEqual(
            director.visitedBeats, CinematicBeat.allCases,
            "collapsing the motion must not drop a beat")
        XCTAssertEqual(cues.events.filter { $0 == .musicStarted }.count, 1)
        XCTAssertTrue(cues.effects.contains(.swoosh))
        XCTAssertTrue(cues.effects.contains(.chime))
    }

    @MainActor
    func testReduceMotionRevealsTheWholeQuestionWithoutTyping() async throws {
        let (director, _) = makeDirector(timing: .reduced)
        _ = try await runToEnd(director)

        XCTAssertEqual(director.typedQuestion, CinematicDirector.question)
    }

    @MainActor
    func testTheQuestionIsFullyTypedByTheEndOfTheStandardRun() async throws {
        let (director, _) = makeDirector()
        _ = try await runToEnd(director)

        XCTAssertEqual(director.typedQuestion, CinematicDirector.question)
        XCTAssertFalse(CinematicDirector.question.isEmpty)
    }

    // MARK: - Beat 5

    func testAnEmptyStoreStillProducesAValidBeatFive() {
        let cards = CinematicFrameSelection.cards(from: [], slots: CinematicGrid.slots)

        XCTAssertEqual(cards.count, CinematicGrid.slots, "a fresh install still gets a full grid")
        XCTAssertTrue(cards.allSatisfy(\.isPlaceholder))
        XCTAssertTrue(
            cards.allSatisfy { $0.appName == nil },
            "a placeholder never names an app — that would be a fabricated screenshot")
        XCTAssertEqual(Set(cards.map(\.id)).count, cards.count, "ids stay unique for ForEach")
    }

    @MainActor
    func testDirectorSeedsPlaceholdersBeforeAnyFrameIsRead() async throws {
        let (director, _) = makeDirector()
        director.start { _ in }

        XCTAssertEqual(director.cards.count, CinematicGrid.slots)
        XCTAssertTrue(
            director.cards.allSatisfy(\.isPlaceholder),
            "beat 5 is valid before the store has been touched")
        director.skip()
    }

    func testRealFramesReplaceEveryPlaceholderRatherThanSomeOfThem() {
        let frames = [Self.frame(id: 7, at: 1_000), Self.frame(id: 9, at: 1_100)]
        let cards = CinematicFrameSelection.cards(from: frames, slots: CinematicGrid.slots)

        XCTAssertEqual(cards.count, 2, "two frames means two cards, not two plus four grey holes")
        XCTAssertTrue(cards.allSatisfy { !$0.isPlaceholder })
        XCTAssertEqual(cards.map(\.id), [7, 9])
    }

    func testFramesAreSampledAcrossTheWindowRatherThanTakenFromTheEnd() {
        // One app for the whole window, so the app-diversity pass contributes a single frame and the
        // even spread has to do the rest.
        let frames = (0..<60).map { Self.frame(id: Int64($0), at: 1_000 + Double($0) * 2) }
        let cards = CinematicFrameSelection.cards(from: frames, slots: 6)

        XCTAssertEqual(cards.count, 6)
        XCTAssertEqual(Set(cards.map(\.id)).count, 6, "no frame is shown twice")
        XCTAssertEqual(
            cards.map(\.id).sorted(), cards.map(\.id),
            "the grid fills oldest first")
        XCTAssertLessThan(
            try XCTUnwrap(cards.map(\.id).min()), 20,
            "spread across the window: the six most recent frames are six pictures of one window")
        XCTAssertGreaterThan(try XCTUnwrap(cards.map(\.id).max()), 40)
    }

    func testTheGridPrefersOneFramePerAppOverSixOfTheSameOne() {
        // What a real hour looks like: fifty frames of one editor, a couple of everything else. The
        // first render on this machine's own store came back five-of-six identical, which is what
        // this rule exists to stop.
        var frames: [RewindFrame] = []
        for index in 0..<50 {
            frames.append(Self.frame(id: Int64(index), at: 1_000 + Double(index), app: "Cursor"))
        }
        frames.append(Self.frame(id: 100, at: 1_060, app: "Arc"))
        frames.append(Self.frame(id: 101, at: 1_061, app: "Terminal"))
        frames.append(Self.frame(id: 102, at: 1_062, app: "Mail"))

        let cards = CinematicFrameSelection.cards(from: frames, slots: 6)
        let apps = cards.compactMap(\.appName)

        XCTAssertEqual(cards.count, 6)
        XCTAssertEqual(
            Set(apps), ["Cursor", "Arc", "Terminal", "Mail"],
            "every distinct app is represented before a second frame of any of them")
        XCTAssertEqual(
            apps.filter { $0 == "Cursor" }.count, 3,
            "the remaining slots fill from the app that actually dominated the window")
        XCTAssertTrue(cards.allSatisfy { !$0.isPlaceholder }, "still every card a real frame")
    }

    func testSelectionIsDeterministic() {
        var frames: [RewindFrame] = []
        for index in 0..<40 {
            let app = ["Cursor", "Arc", "Terminal"][index % 3]
            frames.append(Self.frame(id: Int64(index), at: 1_000 + Double(index), app: app))
        }
        let first = CinematicFrameSelection.cards(from: frames, slots: 6).map(\.id)
        for _ in 0..<20 {
            XCTAssertEqual(
                CinematicFrameSelection.cards(from: frames, slots: 6).map(\.id), first,
                "a grid that differs run to run cannot be reviewed against a screenshot")
        }
    }

    func testFrameSelectionIsBoundedBySlots() {
        let frames = (0..<500).map { Self.frame(id: Int64($0), at: Double($0)) }
        XCTAssertEqual(CinematicFrameSelection.cards(from: frames, slots: 3).count, 3)
        XCTAssertEqual(CinematicFrameSelection.cards(from: frames, slots: 0), [])
        XCTAssertEqual(CinematicFrameSelection.cards(from: frames, slots: -4), [])
    }

    func testEveryCardGetsADistinctSlotInsideTheGrid() {
        for count in 1...CinematicGrid.slots {
            let slots = (0..<count).map { CinematicGrid.slot($0, count: count) }
            XCTAssertEqual(
                Set(slots.map { "\($0.width),\($0.height)" }).count, count,
                "\(count) cards must not stack on each other")

            let half = CinematicGrid.height(for: count) / 2
            for slot in slots {
                XCTAssertLessThanOrEqual(
                    abs(slot.height) + CinematicGrid.cardSize.height / 2, half + 0.001,
                    "a card must sit inside the grid it is laid out in")
            }
        }
    }

    func testTheGridIsExactlyAsWideAsThePromptField() {
        XCTAssertEqual(
            CinematicGrid.width, CinematicVesselMetrics.promptWidth, accuracy: 0.001,
            "the swarm lines up under the field it answers")
    }

    func testCardsFlyInFromOffScreen() {
        let stage = CGSize(width: 1_512, height: 982)
        for index in 0..<CinematicGrid.slots {
            let entry = CinematicGrid.entry(index, count: CinematicGrid.slots, in: stage)
            let travel = (entry.width * entry.width + entry.height * entry.height).squareRoot()
            XCTAssertGreaterThan(
                travel, Double(min(stage.width, stage.height)) / 2,
                "card \(index) has to start outside the frame it flies into")
        }
    }

    func testEntryGeometryIsDeterministic() {
        let stage = CGSize(width: 1_440, height: 900)
        for index in 0..<CinematicGrid.slots {
            XCTAssertEqual(
                CinematicGrid.entry(index, count: 6, in: stage).width,
                CinematicGrid.entry(index, count: 6, in: stage).width,
                "a cinematic that differs run to run cannot be reviewed against a screenshot")
            XCTAssertNotEqual(
                CinematicGrid.entryRotation(index), 0,
                "a card in the air is tilted")
        }
    }

    // MARK: - The run-once gate

    func testTheGateHoldsOnceOnboardingIsDone() {
        XCTAssertFalse(CinematicGate(onboarded: true).shouldPlay)
        XCTAssertTrue(CinematicGate(onboarded: false).shouldPlay)
    }

    func testTheGateReadsTheFlagOnboardingItselfWrites() throws {
        // The same key `OnboardingView` sets and `ContextApp` gates the window on. Its own suite:
        // the machine running the tests is also the machine the app runs on.
        let suite = "com.omi.context-for-claude.CinematicTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { UserDefaults.standard.removePersistentDomain(forName: suite) }

        XCTAssertEqual(CinematicGate.onboardedKey, "context.onboarded")
        XCTAssertTrue(CinematicGate(defaults: defaults).shouldPlay, "a fresh install plays it")

        defaults.set(true, forKey: CinematicGate.onboardedKey)
        XCTAssertFalse(
            CinematicGate(defaults: defaults).shouldPlay,
            "and it never plays a second time")
    }

    // MARK: - Nothing can block onboarding

    func testTheWatchdogDeadlineIsBeyondTheWholeSequence() {
        for timing in [CinematicTiming.standard, .reduced] {
            XCTAssertGreaterThan(
                timing.watchdogDeadline, timing.total,
                "a watchdog inside the run's own budget would truncate the intro")
            XCTAssertEqual(
                timing.watchdogDeadline, timing.total + CinematicTiming.watchdogSlack,
                accuracy: 0.0001)
        }
    }

    @MainActor
    func testAFrameSourceThatNeverAnswersDoesNotHoldTheRunUp() async throws {
        /// Never returns. The sequence must not be waiting on it.
        struct StalledFrames: CinematicFrameSource {
            func recent(limit: Int) async -> [CinematicCard] {
                while !Task.isCancelled { await Task.yield() }
                return []
            }
        }

        let (director, _) = makeDirector(frames: StalledFrames())
        let end = try await runToEnd(director)

        XCTAssertEqual(end, .completed)
        XCTAssertEqual(director.visitedBeats, CinematicBeat.allCases)
        XCTAssertEqual(
            director.cards.count, CinematicGrid.slots,
            "beat 5 kept the placeholders it was seeded with")
    }

    @MainActor
    func testStartingTwiceDoesNotStartTwoRuns() async throws {
        let (director, cues) = makeDirector()
        var handoffs = 0
        director.start { _ in handoffs += 1 }
        director.start { _ in handoffs += 1 }

        try await waitUntil { handoffs > 0 }
        XCTAssertEqual(handoffs, 1)
        XCTAssertEqual(cues.events.filter { $0 == .musicStarted }.count, 1)
    }

    // MARK: - Geometry transcription

    func testTheMarkIsContextMarksGeometryFlippedOnce() {
        // Every value is `ContextMark`'s with y mirrored in the 20-unit box. Asserted rather than
        // trusted because a transcription is exactly the kind of thing that drifts silently: the
        // mark would still *look* like a mark while no longer being the one in the menu bar.
        XCTAssertEqual(CinematicMarkGeometry.box, 20)
        XCTAssertEqual(CinematicMarkGeometry.headCentre.x, 3.4 + 13.2 / 2, accuracy: 0.0001)
        XCTAssertEqual(CinematicMarkGeometry.headCentre.y, 20 - (5.9 + 12.6 / 2), accuracy: 0.0001)
        XCTAssertEqual(CinematicMarkGeometry.headRadii.width, 13.2 / 2, accuracy: 0.0001)
        XCTAssertEqual(CinematicMarkGeometry.headRadii.height, 12.6 / 2, accuracy: 0.0001)
        XCTAssertEqual(CinematicMarkGeometry.headLineWidth, 1.9)
        XCTAssertEqual(CinematicMarkGeometry.legLineWidth, 1.7)

        XCTAssertEqual(CinematicMarkGeometry.eyeCentres.count, 2)
        XCTAssertEqual(CinematicMarkGeometry.eyeCentres.map(\.x), [7.9, 12.1])
        for centre in CinematicMarkGeometry.eyeCentres {
            XCTAssertEqual(centre.y, 20 - (11.0 + 2.1 / 2), accuracy: 0.0001)
        }
        XCTAssertEqual(CinematicMarkGeometry.eyeRadii.width, 1.56 / 2, accuracy: 0.0001)
        XCTAssertEqual(CinematicMarkGeometry.eyeRadii.height, 2.1 / 2, accuracy: 0.0001)

        XCTAssertEqual(CinematicMarkGeometry.legs.count, 2)
        XCTAssertEqual(CinematicMarkGeometry.legs[0].start, CGPoint(x: 7.7, y: 20 - 6.4))
        XCTAssertEqual(CinematicMarkGeometry.legs[0].foot, CGPoint(x: 5.8, y: 20 - 2.6))
        XCTAssertEqual(CinematicMarkGeometry.legs[1].start, CGPoint(x: 12.3, y: 20 - 6.4))
        XCTAssertEqual(CinematicMarkGeometry.legs[1].foot, CGPoint(x: 14.2, y: 20 - 2.6))
    }

    func testTheMarkDrawsInPartsRatherThanAppearingWhole() {
        var draw = CinematicMarkDraw()
        XCTAssertEqual([draw.head, draw.eyes, draw.legs, draw.wordmark], [0, 0, 0, 0])
        XCTAssertEqual(CinematicMarkDraw.complete, CinematicMarkDraw(head: 1, eyes: 1, legs: 1, wordmark: 1))

        draw.head = 1
        XCTAssertNotEqual(draw, .complete, "the head alone is not the mark")
    }

    func testTheVesselStretchesRatherThanBeingReplaced() {
        let mark = CinematicVesselMetrics.metrics(for: .mark)
        let bar = CinematicVesselMetrics.metrics(for: .bar)
        let prompt = CinematicVesselMetrics.metrics(for: .prompt)

        XCTAssertEqual(mark.shellOpacity, 0, "beat 2 shows no shell")
        XCTAssertEqual(bar.shellOpacity, 1)
        XCTAssertGreaterThan(
            prompt.shellSize.width, bar.shellSize.width,
            "beat 4 widens the bar it already is")
        XCTAssertLessThan(bar.markSize, mark.markSize, "the mark shrinks into the bar")
        XCTAssertEqual(bar.wordmarkOpacity, 0, "and the wordmark becomes the bar")
        XCTAssertEqual(prompt.questionOpacity, 1)
        XCTAssertEqual(mark.questionOpacity, 0)
        XCTAssertEqual(
            prompt.shellSize.width, CinematicVesselMetrics.promptWidth,
            "the prompt is the width the grid is laid out against")
    }

    func testTheCaretBlinksOnMacOSCadence() {
        let start = Date(timeIntervalSinceReferenceDate: 0)
        let half = CinematicCaret.blinkSeconds / 2
        XCTAssertTrue(CinematicCaret.isOn(at: start))
        XCTAssertFalse(CinematicCaret.isOn(at: start.addingTimeInterval(half + 0.01)))
        XCTAssertTrue(CinematicCaret.isOn(at: start.addingTimeInterval(2 * half + 0.01)))
    }
}
