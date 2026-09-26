import AppKit
import ContextCore
import SwiftUI
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

    @MainActor
    private func makeDirector(
        timing: CinematicTiming = .standard
    ) -> (CinematicDirector, RecordingCues) {
        let cues = RecordingCues()
        let director = CinematicDirector(
            timing: timing,
            cues: cues,
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
    func testOneSwooshPerWindow() async throws {
        let (director, cues) = makeDirector()
        _ = try await runToEnd(director)

        XCTAssertEqual(
            cues.effects.filter { $0 == .swoosh }.count,
            1 + director.windows.count,
            "the stretch, plus one swoosh per window that flew in")
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

    /// The regression this beat exists to have caught.
    ///
    /// Beat 5 used to read the capture store and fall back to a grey skeleton when it was empty.
    /// Every first-run user has an empty store — the cinematic is gated on `context.onboarded` and
    /// capture is not granted until Phase 4 — so the fallback was what shipped. There is now one
    /// path, and this asserts a cold start reaches it with a full composition.
    @MainActor
    func testAColdStoreStillProducesAFullBeatFive() async throws {
        let (director, _) = makeDirector()
        director.start { _ in }
        defer { director.skip() }

        XCTAssertEqual(
            director.windows.count, CinematicGrid.slots,
            "a brand-new install gets every slot filled, not a partial grid")
        XCTAssertEqual(
            Set(director.windows.map(\.id)).count, director.windows.count,
            "ids stay unique for ForEach")
        XCTAssertEqual(
            Set(director.windows.map(\.layout)).count, director.windows.count,
            "no two windows in the grid are the same drawing")
    }

    /// The composition is complete the instant `start()` returns: there is no read to be raced and
    /// nothing that can arrive late, which is what removed the empty-grid failure rather than
    /// papering over it.
    @MainActor
    func testTheCompositionIsCompleteBeforeAnyBeatHasPlayed() async throws {
        let (director, _) = makeDirector()
        director.start { _ in }
        defer { director.skip() }

        XCTAssertEqual(director.windows, CinematicWindowDeck.windows(count: CinematicGrid.slots))
        XCTAssertEqual(director.settledCards, 0, "complete, and not yet arrived")
    }

    /// **No fabricated personal content.** The primary guarantee is the type: no case of
    /// `CinematicWindowLayout` and no field of `CinematicWindowSpec` carries a `String`, so a
    /// window has nothing to say a name, an address, or a message with. This walks the shipping
    /// deck through an exhaustive switch, so adding a text-bearing case fails to compile here.
    func testNoSyntheticWindowCanCarryPersonalContent() {
        for window in CinematicWindowDeck.windows(count: CinematicGrid.slots) {
            switch window.layout {
            case .document(let heading, let lines):
                XCTAssertGreaterThan(heading, 0)
                XCTAssertFalse(lines.isEmpty)
            case .media(let cover, let captions):
                XCTAssertGreaterThan(cover, 0)
                XCTAssertFalse(captions.isEmpty)
            case .chat(let turns):
                XCTAssertFalse(turns.isEmpty)
            case .terminal(let rows):
                XCTAssertFalse(rows.isEmpty)
            case .feed(let rows):
                XCTAssertGreaterThan(rows, 0)
            case .gallery(let columns, let rows):
                XCTAssertGreaterThan(columns * rows, 0)
            case .chart(let bars):
                XCTAssertFalse(bars.isEmpty)
            case .sidebar(let rail, let lines):
                XCTAssertFalse(rail.isEmpty)
                XCTAssertFalse(lines.isEmpty)
            }
        }
    }

    /// A **static tripwire**, not behavioural coverage: it reads the drawing's source and asserts
    /// no view in it can put glyphs on screen. The type check above is the real guard; this catches
    /// the other way the rule breaks — a `Text` added straight into a window body.
    func testTheWindowDrawingHasNoTextInIt() throws {
        let source = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // ContextAppTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // package root
            .appendingPathComponent("Sources/ContextApp/Onboarding/CinematicWindowArt.swift")
        let text = try String(contentsOf: source, encoding: .utf8)

        for banned in ["Text(", "Label(", "Image(", "SF Symbol"] {
            XCTAssertFalse(
                text.contains(banned),
                "a synthetic window must not be able to draw \(banned) — see the file's header")
        }
    }

    func testTheDeckIsDeterministicAndTotal() {
        let first = CinematicWindowDeck.windows(count: CinematicGrid.slots)
        for _ in 0..<20 {
            XCTAssertEqual(
                CinematicWindowDeck.windows(count: CinematicGrid.slots), first,
                "a grid that differs run to run cannot be reviewed against a screenshot")
        }
        XCTAssertEqual(CinematicWindowDeck.windows(count: 0), [])
        XCTAssertEqual(CinematicWindowDeck.windows(count: -3), [])
        XCTAssertEqual(
            CinematicWindowDeck.windows(count: 20).count, 20,
            "more slots than archetypes cycles rather than truncating")
    }

    // MARK: - The float

    /// Reduce Motion gets a *static* composition: no drift, no parallax, one fixed frame.
    func testReduceMotionStopsTheFloatEntirely() {
        XCTAssertFalse(
            CinematicWindowMotion.allowsDrift(crossFade: false, reduceMotion: true),
            "the workspace setting alone stops the float")
        XCTAssertFalse(
            CinematicWindowMotion.allowsDrift(crossFade: true, reduceMotion: false),
            "so does the director's reduced timing table")
        XCTAssertFalse(CinematicWindowMotion.allowsDrift(crossFade: true, reduceMotion: true))
        XCTAssertTrue(CinematicWindowMotion.allowsDrift(crossFade: false, reduceMotion: false))

        XCTAssertEqual(CinematicWindowDrift.still.dx, 0)
        XCTAssertEqual(CinematicWindowDrift.still.dy, 0)
        XCTAssertEqual(CinematicWindowDrift.still.rotation, 0)
    }

    /// The float is bounded and out of step. Bounded, because a window that wandered would leave
    /// its slot and break the grid; out of step, because six windows on one period read as a single
    /// sheet rather than as a field.
    func testTheFloatIsBoundedAndNeverInStep() {
        var seen: [[CGFloat]] = []
        for phase in stride(from: 0.0, through: 24.0, by: 0.25) {
            var atThisPhase: [CGFloat] = []
            for index in 0..<CinematicGrid.slots {
                let depth = CinematicGrid.depth(index)
                let drift = CinematicWindowMotion.drift(index: index, at: phase, depth: depth)
                XCTAssertLessThanOrEqual(
                    abs(drift.dy), CinematicWindowMotion.verticalAmplitude * depth + 0.001,
                    "a floating window must stay inside its slot")
                XCTAssertLessThanOrEqual(
                    abs(drift.dx), CinematicWindowMotion.horizontalAmplitude * depth + 0.001)
                XCTAssertLessThanOrEqual(
                    abs(drift.rotation),
                    CinematicWindowMotion.rotationAmplitude * Double(depth) + 0.001)
                // Small enough that the grid still reads as a grid: a tenth of the gap between
                // two windows, not a card that wanders out of its slot.
                XCTAssertLessThan(
                    abs(drift.dy), CinematicGrid.gap / 2,
                    "a window that drifts half a gutter has left its slot")
                atThisPhase.append(drift.dy)
            }
            XCTAssertGreaterThan(
                Set(atThisPhase.map { ($0 * 1_000).rounded() }).count, 1,
                "at \(phase)s every window sat at the same height")
            seen.append(atThisPhase)
        }
        XCTAssertGreaterThan(seen.count, 90, "sampled across more than one full cycle")
    }

    /// Pure, so the composition at a moment is a value a review can be run against.
    func testTheFloatIsAFunctionOfTheClockAlone() {
        for index in 0..<CinematicGrid.slots {
            XCTAssertEqual(
                CinematicWindowMotion.drift(index: index, at: 3.5),
                CinematicWindowMotion.drift(index: index, at: 3.5))
        }
        XCTAssertEqual(CinematicWindowMotion.drift(index: -1, at: 3.5), .still)
    }

    /// The near windows move more than the far ones — the page's parallax, taken from the same
    /// resting scale that sets it.
    func testNearerWindowsCarryMoreOfTheFloat() {
        let depths = (0..<CinematicGrid.slots).map(CinematicGrid.depth)
        XCTAssertGreaterThan(
            try XCTUnwrap(depths.max()), try XCTUnwrap(depths.min()),
            "a field with one depth has no parallax")
        for index in 0..<CinematicGrid.slots {
            XCTAssertGreaterThan(CinematicGrid.restScale(index), 0.9)
            XCTAssertLessThanOrEqual(CinematicGrid.restScale(index), 1)
            XCTAssertNotEqual(
                CinematicGrid.restRotation(index), 0,
                "a settled window keeps a tilt: that is what makes the grid read as a field")
            XCTAssertLessThanOrEqual(abs(CinematicGrid.restRotation(index)), 2.2)
        }
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

    /// The sequence's path has no I/O left on it at all, which is the strongest version of
    /// "decoration cannot block onboarding": there is no read to time out and no task to race.
    @MainActor
    func testTheRunHasNothingToWaitOn() async throws {
        let (director, _) = makeDirector()
        let end = try await runToEnd(director)

        XCTAssertEqual(end, .completed)
        XCTAssertEqual(director.visitedBeats, CinematicBeat.allCases)
        XCTAssertEqual(
            director.windows.count, CinematicGrid.slots,
            "beat 5 played the whole composition it was seeded with")
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

    // MARK: - Vertical alignment

    /// Everything in the prompt bar sits on the shell's centre, which is where the mark already is.
    ///
    /// Rendered rather than asserted on constants, because the defect this pins is not visible in
    /// one. `questionField` used to be an `HStack(alignment: .firstTextBaseline)` containing a caret
    /// that is a `Rectangle`, and SwiftUI resolves the text baselines of a view holding no text to
    /// its own bottom edge — so the caret hung its whole bar above the baseline (4 pt higher than
    /// the line it belongs to) and the stack's inflated above-baseline extent carried the question
    /// 2 pt below the mark. Both numbers came out of a render, so a render is what guards them.
    ///
    /// Each measurement is the *difference* between two renders of the real `CinematicVessel`, so
    /// the shell and the mark cancel and only the thing under test survives. Nothing here needs the
    /// bundled faces: `InkType.prose` is 17 pt, under `Font.inkDisplayThreshold`, so it resolves to
    /// the system font on any machine — and the wordmark, which is the one bundled role in the
    /// vessel, is at zero opacity in `.prompt` and identical in both renders regardless.
    /// The caret's height is a *derived* constant, and nothing else notices when it goes stale:
    /// centring keeps text and caret on the same centre whatever the bar's height, so the centring
    /// test below stays green while the caret is quietly the wrong size for its line. That is
    /// exactly what happened when `InkType.prose` went 15 pt → 17 pt and `barHeight` stayed 19.
    ///
    /// So derive it here from the face itself rather than restating the number: TextKit rounds the
    /// ascender and descender away from the baseline, and the line box is their sum. Resizing prose
    /// without recomputing `barHeight` now fails.
    func testTheCaretIsExactlyTheLineBoxOfTheRoleItSitsIn() {
        // Deliberately *not* `InkTextStyle.naturalLineHeight`: that is the face's own line height
        // (20.02 at 17 pt) and it is not the box SwiftUI lays a `Text` out in. TextKit rounds the
        // ascender and the descender away from the baseline independently, so the laid-out box is
        // `ceil(ascender) + ceil(descender)` — 21 — and it is that box the caret has to match.
        // Asserting the wrong one of the two would pass while the caret stayed a point short.
        //
        // prose is under `Font.inkDisplayThreshold`, so it resolves to the system face on any
        // machine — the same reason the render test above can rely on it.
        let face = NSFont.systemFont(ofSize: InkType.prose.size)
        let lineBox = ceil(face.ascender) + ceil(-face.descender)
        XCTAssertEqual(
            CinematicCaret.barHeight, lineBox, accuracy: 0.01,
            "InkType.prose is \(InkType.prose.size) pt, whose laid-out line box is \(lineBox) — "
                + "CinematicCaret.barHeight must follow it, not the size prose used to be")
    }

    @MainActor
    func testThePromptCentresTheQuestionAndTheCaretOnTheShell() throws {
        let stageCentre = CinematicVesselMetrics.stageHeight / 2
        let blank = try render(question: "", showsCaret: false)

        let caret = try XCTUnwrap(
            Self.changedRows(blank, try render(question: "", showsCaret: true)),
            "the caret drew nothing to measure")
        XCTAssertEqual(
            caret.bottom - caret.top, CinematicCaret.barHeight, accuracy: 0.5,
            "the caret is one line box tall, which is what lets it be centred rather than sat on a "
                + "baseline")
        XCTAssertEqual(
            (caret.top + caret.bottom) / 2, stageCentre, accuracy: 0.5,
            "the caret straddles the shell's centre rather than hanging above it")

        // "H" is a cap-height glyph with no descender, so the bottom of its ink is the baseline
        // exactly. The line box around that baseline follows from the face's own metrics — and it is
        // the line box, not the ink, that has to be centred, because the caret and the mark are
        // centred on their boxes too.
        let glyph = try XCTUnwrap(
            Self.changedRows(blank, try render(question: "H", showsCaret: false)),
            "the question drew nothing to measure")
        let face = NSFont.systemFont(ofSize: InkType.prose.size, weight: .regular)
        XCTAssertEqual(
            glyph.bottom - (face.ascender + face.descender) / 2, stageCentre, accuracy: 0.75,
            "the question's line box sits on the shell's centre, where the mark is")

        // The render above is `.prompt`, and `.bar` is the same field in a shorter shell: the
        // question is laid out in a frame the height of `shellSize` and centred in it, so the one
        // thing that could still part the two is the mark leaving the centre the field is centred
        // on. It does not, in either form — which is what makes one render cover both.
        for form in [CinematicForm.bar, .prompt] {
            XCTAssertEqual(
                CinematicVesselMetrics.metrics(for: form).markOffset.height, 0,
                "the mark is on the shell's centre in \(form)")
        }
    }

    /// A bitmap and the scale it was drawn at, so a row index can be read back as a point.
    private struct Bitmap {
        let width: Int
        let height: Int
        let scale: CGFloat
        let bytes: [UInt8]
    }

    /// The vessel in its `.prompt` form at 4×, so one pixel is a quarter of a point. Black behind
    /// it only so the white ink has something to differ from; it changes no layout.
    @MainActor
    private func render(question: String, showsCaret: Bool) throws -> Bitmap {
        let scale: CGFloat = 4
        let renderer = ImageRenderer(
            content: ZStack {
                Color.black
                CinematicVessel(
                    draw: .complete,
                    form: .prompt,
                    question: question,
                    showsCaret: showsCaret,
                    // Static: a `TimelineView` caret would render a different frame each run.
                    animatesCaret: false)
            }
            .frame(
                width: CinematicVesselMetrics.promptWidth,
                height: CinematicVesselMetrics.stageHeight))
        renderer.scale = scale

        let image = try XCTUnwrap(renderer.cgImage, "ImageRenderer produced no bitmap")
        var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
        let drew = bytes.withUnsafeMutableBytes { raw -> Bool in
            guard
                let context = CGContext(
                    data: raw.baseAddress,
                    width: image.width,
                    height: image.height,
                    bitsPerComponent: 8,
                    bytesPerRow: image.width * 4,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
            else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            return true
        }
        XCTAssertTrue(drew, "could not back the render with a bitmap")
        return Bitmap(width: image.width, height: image.height, scale: scale, bytes: bytes)
    }

    /// The band of rows two renders disagree in, in points from the top of the stage. Nil when they
    /// are identical, which for these pairs means the thing under test never drew.
    private static func changedRows(_ a: Bitmap, _ b: Bitmap) -> (top: CGFloat, bottom: CGFloat)? {
        guard a.width == b.width, a.height == b.height else { return nil }
        var first: Int?
        var last: Int?
        for y in 0..<a.height {
            for x in 0..<a.width {
                let i = (y * a.width + x) * 4
                // 8/255 keeps the faintest antialiased edge out of the band symmetrically, which
                // moves neither the centre nor the height by more than a pixel.
                let differs = (0..<3).contains {
                    abs(Int(a.bytes[i + $0]) - Int(b.bytes[i + $0])) > 8
                }
                if differs {
                    first = first ?? y
                    last = y
                    break
                }
            }
        }
        guard let first, let last else { return nil }
        return (CGFloat(first) / a.scale, CGFloat(last + 1) / a.scale)
    }
}
