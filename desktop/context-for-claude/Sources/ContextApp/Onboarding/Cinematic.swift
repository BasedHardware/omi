import AppKit
import Combine
import SwiftUI

//  The first-run cinematic — Phase 3 of docs/first-run-experience.md.
//
//  Six beats over ~8.6 s, on one borderless window covering the display under the pointer, which
//  then shrinks into the 720×640 welcome card (`OnboardingWindow`). Every beat carries a sound.
//
//      1  dim      the desktop darkens; the bed fades in
//      2  mark     the mark draws itself on — head, eyes, legs — then the wordmark resolves
//      3  bar      mark and wordmark collapse into a single horizontal bar
//      4  prompt   the bar stretches into a prompt field and a question types itself
//      5  windows  window cards fly in on staggered swooshes and settle into a grid
//      6  recede   everything scales toward the card's footprint and hands off
//
//  Three rules shape the whole file:
//
//  - **Decoration must never be able to block onboarding.** Nothing here throws, nothing here
//    waits on I/O, and `CinematicDirector.finish` is latched and idempotent — Esc, the Skip
//    button, the last beat and the watchdog all land in the same terminal state exactly once. Beat
//    5's windows are drawn rather than read (`CinematicWindows.swift`), so there is no I/O on the
//    sequence's path at all — not a read that is raced, a read that does not exist.
//  - **The sequence is a value, the timing is a value, and the cues go through a seam.** So the
//    part worth testing — beat order, abort from any beat, reduce-motion collapse, which sound
//    belongs to which beat — runs with no window, no clock and no audio device.
//  - **Reduce Motion collapses every beat to a cross-fade.** One timing table
//    (`CinematicTiming.reduced`) does it, so honouring the setting is a lookup rather than a
//    discipline kept beat by beat.

// MARK: - Beats

/// The six beats, in the only order they ever run.
enum CinematicBeat: Int, CaseIterable, Comparable, Sendable {
    case dim = 0
    case mark
    case bar
    case prompt
    case windows
    case recede

    static func < (lhs: CinematicBeat, rhs: CinematicBeat) -> Bool {
        lhs.rawValue < rhs.rawValue
    }

    /// The beat after this one, or `nil` at the end of the sequence.
    var next: CinematicBeat? { CinematicBeat(rawValue: rawValue + 1) }

    /// For logs. Never shown to the user.
    var name: String {
        switch self {
        case .dim: return "dim"
        case .mark: return "mark"
        case .bar: return "bar"
        case .prompt: return "prompt"
        case .windows: return "windows"
        case .recede: return "recede"
        }
    }
}

/// How the run ended. Every case is terminal, and every case hands off to the welcome card —
/// there is deliberately no "failed" outcome, because a cinematic that fails still owes the user
/// their onboarding.
enum CinematicEnd: Equatable, Sendable {
    /// All six beats played.
    case completed
    /// Esc, or the "Skip intro" button, during this beat.
    case skipped(CinematicBeat)
    /// The watchdog fired: something stalled past the whole sequence's budget. Should never
    /// happen; exists so that if it does, onboarding still arrives.
    case expired(CinematicBeat)

    /// The beat the run was in when it ended.
    var beat: CinematicBeat {
        switch self {
        case .completed: return .recede
        case .skipped(let beat), .expired(let beat): return beat
        }
    }

    /// True when the user asked for the intro to stop. The bed still fades rather than cutting;
    /// this only distinguishes *why* it stopped.
    var wasInterrupted: Bool {
        if case .completed = self { return false }
        return true
    }
}

/// Where the run is. `idle` before `start()`, `ended` after exactly one terminal transition.
enum CinematicStage: Equatable, Sendable {
    case idle
    case playing(CinematicBeat)
    case ended(CinematicEnd)

    var isTerminal: Bool {
        if case .ended = self { return true }
        return false
    }

    /// The beat on screen, or `nil` before the first one and after the last.
    var beat: CinematicBeat? {
        if case .playing(let beat) = self { return beat }
        return nil
    }
}

/// The beat order, as a value, with no clock and no view attached.
///
/// Separate from `CinematicDirector` because ordering and abort are the two things worth asserting
/// and neither needs a display: a test walks this the same way the director does.
struct CinematicSequence: Equatable, Sendable {
    private(set) var stage: CinematicStage = .idle
    /// Every beat the run has entered, in order. The director copies this into its log line, and
    /// tests assert against it rather than against a schedule of sleeps.
    private(set) var visited: [CinematicBeat] = []

    init() {}

    /// Enters the next beat, or ends the run after the last one. A no-op once terminal, so a late
    /// timer cannot walk a finished sequence forward.
    ///
    /// - Returns: the beat now playing, or `nil` when this call ended the run (or found it ended).
    @discardableResult
    mutating func advance() -> CinematicBeat? {
        switch stage {
        case .ended:
            return nil
        case .idle:
            return enter(CinematicBeat.allCases[0])
        case .playing(let beat):
            guard let next = beat.next else {
                stage = .ended(.completed)
                return nil
            }
            return enter(next)
        }
    }

    /// Esc or "Skip intro". Records the beat it interrupted. Idempotent.
    @discardableResult
    mutating func abort() -> CinematicEnd? {
        end(with: .skipped(stage.beat ?? CinematicBeat.allCases[0]))
    }

    /// The watchdog. Idempotent, and never overwrites an end that already happened.
    @discardableResult
    mutating func expire() -> CinematicEnd? {
        end(with: .expired(stage.beat ?? CinematicBeat.allCases[0]))
    }

    private mutating func end(with end: CinematicEnd) -> CinematicEnd? {
        guard !stage.isTerminal else { return nil }
        stage = .ended(end)
        return end
    }

    private mutating func enter(_ beat: CinematicBeat) -> CinematicBeat {
        stage = .playing(beat)
        visited.append(beat)
        return beat
    }
}

// MARK: - Timing

/// Seconds per beat, plus the sub-beat divisions beats 2, 4 and 5 need.
///
/// A table rather than constants scattered through the director, because Reduce Motion is a
/// *different table* and not a set of `if` statements: `reduced` collapses every beat to one
/// cross-fade, and the director reads whichever table it was handed without knowing which it got.
struct CinematicTiming: Equatable, Sendable {
    var dim: Double
    var mark: Double
    var bar: Double
    var prompt: Double
    var windows: Double
    var recede: Double

    /// Beat 2, in order: the head's stroke, the eyes popping in, the legs' stroke, the hold before
    /// the wordmark, and the wordmark resolving. Sums to `mark`.
    var head: Double
    var eyes: Double
    var legs: Double
    var markHold: Double
    var wordmark: Double

    /// Beat 4: the stretch, then the question typing itself, then the hold before beat 5.
    var stretch: Double
    var typing: Double
    var promptHold: Double

    /// Beat 5: one card's flight, and the gap between two cards leaving.
    var cardFlight: Double
    var cardStagger: Double

    /// True when this table is the Reduce Motion one — every beat one cross-fade, no travel.
    var isCrossFade: Bool

    /// The full run.
    var total: Double { dim + mark + bar + prompt + windows + recede }

    /// When the watchdog gives up and hands off to the card anyway.
    ///
    /// Generous on purpose: it exists to guarantee onboarding arrives if a beat somehow stalls,
    /// not to police the pacing. A watchdog tight enough to fire during a slow frame would be a
    /// bug that truncates the intro on exactly the machines least able to spare the goodwill.
    var watchdogDeadline: Double { total + Self.watchdogSlack }

    static let watchdogSlack: Double = 6

    func duration(of beat: CinematicBeat) -> Double {
        switch beat {
        case .dim: return dim
        case .mark: return mark
        case .bar: return bar
        case .prompt: return prompt
        case .windows: return windows
        case .recede: return recede
        }
    }

    /// The shipping pacing. Beat 2 is the longest because it is the moment the app introduces
    /// itself, and the spec asks it to hold.
    static let standard = CinematicTiming(
        dim: 0.60,
        mark: 2.40,
        bar: 0.70,
        prompt: 2.05,
        windows: 2.10,
        recede: 0.75,
        head: 0.70,
        eyes: 0.30,
        legs: 0.55,
        markHold: 0.25,
        wordmark: 0.60,
        stretch: 0.55,
        typing: 1.15,
        promptHold: 0.35,
        cardFlight: 0.60,
        cardStagger: 0.13,
        isCrossFade: false)

    /// Reduce Motion. Every beat is the same short cross-fade, every sub-beat is that cross-fade
    /// too, and nothing travels: the beats still *happen*, in order, with their sounds — the run is
    /// a slideshow of the same six states rather than a sequence of moves.
    static let reduced = CinematicTiming(
        dim: crossFade,
        mark: crossFade,
        bar: crossFade,
        prompt: crossFade,
        windows: crossFade,
        recede: crossFade,
        head: crossFade,
        eyes: crossFade,
        legs: crossFade,
        markHold: 0,
        wordmark: crossFade,
        stretch: crossFade,
        typing: 0,
        promptHold: 0,
        cardFlight: crossFade,
        cardStagger: 0,
        isCrossFade: true)

    /// Long enough to read as a change of state, short enough that six of them are not a wait.
    static let crossFade: Double = 0.30

    /// The table for the machine as it is configured right now. `nonisolated`, because it is a
    /// default argument and those are evaluated outside the callee's actor.
    static var current: CinematicTiming {
        InkReduceMotion.isEnabled ? .reduced : .standard
    }
}

// MARK: - Sound

/// Which cue belongs to which beat.
///
/// A table, so "every beat has a sound" is a fact a test can check rather than a claim in a
/// comment. The bed is not in here: it is started by beat 1 and stopped once, at the end, and is
/// therefore lifecycle rather than a cue.
enum CinematicCue {
    /// The one-shot that marks a beat's arrival.
    static func effect(for beat: CinematicBeat) -> SoundEffect {
        switch beat {
        // Beat 1 is the bed arriving; the click is the shutter that starts it.
        case .dim: return .click
        // Four ticks as the strokes land — see `CinematicDirector.playMark`.
        case .mark: return .click
        // Two things becoming one.
        case .bar: return .click
        // The spec's swoosh, on the stretch.
        case .prompt: return .swoosh
        // One per card, staggered.
        case .windows: return .swoosh
        // The completion cue: the world has changed and the app is here.
        case .recede: return .chime
        }
    }
}

/// Everything the director asks of the audio layer.
///
/// A seam, so the cue *decisions* — one per beat, a swoosh per card, and a fade rather than a cut
/// on abort — are asserted without an audio device. `Sound` already gates chrome on the system
/// UI-sound setting and already degrades to silence, so nothing here gates anything a second time.
@MainActor
protocol CinematicCues: AnyObject {
    /// Warm the decoders so the first click of the cinematic is not the one that pays for them.
    func prepare()
    func startMusic()
    func stopMusic(fadeOut: TimeInterval)
    func play(_ effect: SoundEffect)
    /// The bed's own mute control — the one the spec says governs it, since the system's UI-sound
    /// switch governs chrome and the bed is content. Persisted by `SoundController`.
    var isMusicEnabled: Bool { get }
    func setMusicEnabled(_ enabled: Bool)
}

/// `CinematicCues` on the real `Sound`.
@MainActor
final class SystemCinematicCues: CinematicCues {
    /// `nonisolated` so this can be a default argument: there is no state to initialise, and a
    /// default argument is evaluated outside the main actor even when the callee is on it.
    nonisolated init() {}

    func prepare() { Sound.prepare() }
    func startMusic() { Sound.music.start() }
    func stopMusic(fadeOut: TimeInterval) { Sound.music.stop(fadeOut: fadeOut) }
    func play(_ effect: SoundEffect) { Sound.effect(effect) }

    var isMusicEnabled: Bool { Sound.music.isEnabled }

    /// Turning it off fades the bed out (`SoundController` does that itself); turning it back on has
    /// to restart it, because nothing else is going to.
    func setMusicEnabled(_ enabled: Bool) {
        Sound.music.isEnabled = enabled
        if enabled { Sound.music.start() }
    }
}

// MARK: - The run-once gate

/// Whether this install has already been onboarded.
///
/// Reads `context.onboarded`, the flag `OnboardingView` sets when the flow finishes and
/// `ContextApp` already gates the window on — this only ever reads it. There is exactly one writer
/// of the *true* value (`OnboardingView.sealTheRun`) and exactly one clearer (`OnboardingReset`, the
/// Settings row that starts setup over); nothing else in the product touches it.
///
/// The cinematic is gated separately from the window because the two questions have different
/// answers. Settings' "Run setup again" is the deliberate case that wants the intro — it spends both
/// records, so this gate reads a genuine first run and plays — and a *resumed* run is the case that
/// must not have it, which is the paragraph on `shouldPlay` below.
struct CinematicGate {
    /// Set by `OnboardingView`, cleared by `OnboardingReset`. Read-only here.
    static let onboardedKey = "context.onboarded"

    private let defaults: UserDefaults?
    /// Set only by the testing initialiser, which stands in for the whole read.
    private let resolved: Bool?

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.resolved = nil
    }

    /// For tests, and for a caller that has already read the flag.
    init(onboarded: Bool) {
        self.defaults = nil
        self.resolved = onboarded
    }

    /// Read at the moment it is asked, not at construction: the flag is written by the flow this
    /// gates, and a value cached in an initialiser would be the wrong one by the time it mattered.
    ///
    /// **A resumed run is not a first run.** Screen Recording only applies to a process that already
    /// had it at launch, so onboarding restarts the app on purpose — and the process that comes back
    /// still has `context.onboarded` unset, because the flow it is resuming has not finished. Reading
    /// that flag alone, this gate saw a fresh install and replayed the eight-second intro over a user
    /// who was four cards in: *"it goes to the initial cinematic intro and everything, and I have to
    /// go through everything again."*
    ///
    /// `OnboardingResume` is the other half of the same question, so it is asked here rather than
    /// left to the caller. "Has this install been onboarded" and "is a run already under way" are
    /// both reasons not to play, and a gate that knows only one of them is wrong every time the other
    /// applies.
    var shouldPlay: Bool {
        if let resolved { return !resolved }
        guard let defaults else { return true }
        guard !defaults.bool(forKey: Self.onboardedKey) else { return false }
        return OnboardingResume(defaults: defaults).step == nil
    }
}

// MARK: - Animatable state

/// How much of each part of the mark has been drawn. Beat 2 walks this from all-zero to
/// `.complete`.
struct CinematicMarkDraw: Equatable, Sendable {
    /// Stroke-end along the head's outline, starting at the top and going clockwise.
    var head: Double = 0
    /// The eyes are *fills* in the mark's geometry, so they scale in rather than stroking on.
    var eyes: Double = 0
    /// Stroke-end down each leg, from the head towards the foot.
    var legs: Double = 0
    /// The wordmark resolving under it.
    var wordmark: Double = 0

    static let complete = CinematicMarkDraw(head: 1, eyes: 1, legs: 1, wordmark: 1)
}

/// What the mark-and-wordmark object currently *is*. One object through all three: the views never
/// change identity, so SwiftUI interpolates the geometry itself and there is nothing to match.
enum CinematicForm: Equatable, Sendable {
    /// Beat 2: the mark large and centred, the wordmark under it.
    case mark
    /// Beat 3: a single horizontal bar.
    case bar
    /// Beats 4–5: the bar stretched into a prompt field.
    case prompt
}

// MARK: - Director

/// Runs the six beats and publishes what the view draws.
///
/// Everything that could take an unknown amount of time is kept off the sequence's path: the beat
/// loop only ever awaits `sleep`, and the frames for beat 5 load on their own task and are never
/// awaited. That is what makes the run bounded by construction rather than by a timeout.
@MainActor
final class CinematicDirector: ObservableObject {
    /// The one seam the beat loop waits on. Injected so a test walks the whole sequence in
    /// microseconds without a clock.
    typealias Sleep = @Sendable (Double) async -> Void

    /// `nonisolated`, because it is a default argument and those are evaluated outside the actor.
    nonisolated static let realSleep: Sleep = { seconds in
        guard seconds > 0 else { return }
        try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
    }

    /// The question that types itself in beat 4. From the spec, verbatim.
    static let question = "what was I working on today?"

    /// How the bed leaves. Longer than `SoundMusic.defaultFadeOut` when the run completed, because
    /// then it is dissolving into the welcome card rather than being cut short.
    static let completedFadeOut: TimeInterval = 2.0
    static let interruptedFadeOut: TimeInterval = SoundMusic.defaultFadeOut

    // MARK: Published

    @Published private(set) var stage: CinematicStage = .idle
    /// 0 → 1 across beat 1. The scrim's opacity.
    @Published private(set) var dim: Double = 0
    @Published private(set) var draw = CinematicMarkDraw()
    @Published private(set) var form: CinematicForm = .mark
    /// Characters of `question` shown so far.
    @Published private(set) var typedCount: Int = 0
    /// Beat 5's windows. Fixed, synthetic, and identical on every run — see
    /// `CinematicWindows.swift` for why there is no longer a path that reads the user's frames.
    @Published private(set) var windows: [CinematicWindowSpec] = []
    /// How many windows have arrived. Window `i` is in flight until `i < settledCards`.
    @Published private(set) var settledCards: Int = 0
    /// Beat 5 has made room: the prompt has lifted and the grid's space is open. Never closes.
    @Published private(set) var gridOpen = false
    /// Beat 6.
    @Published private(set) var receding = false
    /// Mirrors the bed's persisted mute control, so the button in the corner reads it.
    @Published private(set) var musicEnabled = true

    // MARK: Injected

    let timing: CinematicTiming
    private let cues: CinematicCues
    private let sleep: Sleep

    // MARK: Private

    private var sequence = CinematicSequence()
    private var runTask: Task<Void, Never>?
    private var watchdogTask: Task<Void, Never>?
    private var onFinish: ((CinematicEnd) -> Void)?
    /// Latched. Esc, the Skip button, the last beat and the watchdog can all arrive; exactly one
    /// of them is allowed to hand off.
    private var didFinish = false

    init(
        timing: CinematicTiming = .current,
        cues: CinematicCues = SystemCinematicCues(),
        sleep: @escaping Sleep = CinematicDirector.realSleep
    ) {
        self.timing = timing
        self.cues = cues
        self.sleep = sleep
        self.musicEnabled = cues.isMusicEnabled
    }

    /// Every beat entered so far, for the log line and for tests.
    var visitedBeats: [CinematicBeat] { sequence.visited }

    /// The question, truncated to what beat 4 has typed.
    var typedQuestion: String {
        String(Self.question.prefix(typedCount))
    }

    /// True once the caret should be visible: it arrives with the prompt and leaves with beat 6.
    var showsCaret: Bool {
        form == .prompt && !receding
    }

    // MARK: Lifecycle

    /// Starts the run. `onFinish` is called exactly once, on the main actor, whatever happens.
    func start(onFinish: @escaping (CinematicEnd) -> Void) {
        guard case .idle = sequence.stage, runTask == nil else { return }
        self.onFinish = onFinish

        cues.prepare()
        // The full composition, immediately. There is nothing to wait for and nothing that can
        // arrive late, which is the whole of the fix for the empty first-run grid.
        windows = CinematicWindowDeck.windows(count: CinematicGrid.slots)
        armWatchdog()

        runTask = Task { [weak self] in
            await self?.run()
        }
    }

    /// Esc, or the "Skip intro" button.
    func skip() {
        guard let end = sequence.abort() else { return }
        stage = sequence.stage
        finish(end)
    }

    /// The bed's mute control. Muting fades it out; unmuting picks it back up where the run is.
    func toggleMusic() {
        cues.setMusicEnabled(!musicEnabled)
        musicEnabled = cues.isMusicEnabled
    }

    // MARK: The beat loop

    private func run() async {
        while let beat = advance() {
            await play(beat)
            if Task.isCancelled { return }
        }
        // `advance()` returned nil without being cancelled: the sequence ran out of beats.
        guard case .ended(let end) = sequence.stage else { return }
        finish(end)
    }

    /// Enters the next beat and mirrors the sequence into `stage` for the view.
    private func advance() -> CinematicBeat? {
        guard !Task.isCancelled else { return nil }
        let beat = sequence.advance()
        stage = sequence.stage
        return beat
    }

    private func play(_ beat: CinematicBeat) async {
        switch beat {
        case .dim: await playDim()
        case .mark: await playMark()
        case .bar: await playBar()
        case .prompt: await playPrompt()
        case .windows: await playWindows()
        case .recede: await playRecede()
        }
    }

    /// Beat 1. The desktop darkens and the bed fades in under it.
    private func playDim() async {
        cues.play(CinematicCue.effect(for: .dim))
        cues.startMusic()
        animate(timing.dim) { self.dim = 1 }
        await sleep(timing.dim)
    }

    /// Beat 2. Head, then eyes, then legs, then — after a held beat — the wordmark.
    ///
    /// Four separate strokes rather than one, because the mark introducing itself part by part is
    /// the whole point of the beat: a single trim across the composite path would draw the head and
    /// the legs as one continuous line, which is not how the drawing is built.
    private func playMark() async {
        cues.play(CinematicCue.effect(for: .mark))
        animate(timing.head) { self.draw.head = 1 }
        await sleep(timing.head)

        cues.play(.click)
        // A touch of overshoot on the eyes: they are fills, and a linear fade would read as an
        // image appearing rather than as two dots being placed.
        animate(timing.eyes, curve: .spring(response: timing.eyes, dampingFraction: 0.62)) {
            self.draw.eyes = 1
        }
        await sleep(timing.eyes)

        cues.play(.click)
        animate(timing.legs) { self.draw.legs = 1 }
        await sleep(timing.legs)

        await sleep(timing.markHold)

        cues.play(.click)
        animate(timing.wordmark) { self.draw.wordmark = 1 }
        await sleep(timing.wordmark)
    }

    /// Beat 3. The mark shrinks into the left of a bar and the wordmark's block becomes the bar.
    private func playBar() async {
        cues.play(CinematicCue.effect(for: .bar))
        animate(timing.bar, curve: .spring(response: timing.bar, dampingFraction: 0.86)) {
            self.form = .bar
        }
        await sleep(timing.bar)
    }

    /// Beat 4. The bar widens into a prompt field, then the question types itself.
    private func playPrompt() async {
        cues.play(CinematicCue.effect(for: .prompt))
        animate(timing.stretch, curve: .spring(response: timing.stretch, dampingFraction: 0.82)) {
            self.form = .prompt
        }
        await sleep(timing.stretch)

        await typeQuestion()
        await sleep(timing.promptHold)
    }

    /// One character at a time, with a keystroke every few characters — every character would be a
    /// stutter, and none at all reads as text being pasted in.
    private func typeQuestion() async {
        let characters = Self.question.count
        guard timing.typing > 0, characters > 0 else {
            typedCount = characters
            return
        }
        let perCharacter = timing.typing / Double(characters)
        for index in 1...characters {
            typedCount = index
            if index.isMultiple(of: Self.keystrokeEvery) { cues.play(.click) }
            await sleep(perCharacter)
            if Task.isCancelled { return }
        }
    }

    /// Every fourth character. At ~38 ms per character that is a keystroke every 150 ms — texture,
    /// not a typewriter.
    private static let keystrokeEvery = 4

    /// Beat 5. Windows arrive one at a time, each on its own swoosh.
    private func playWindows() async {
        let count = windows.count
        guard count > 0 else {
            // No windows at all should be impossible — `start()` seeds the whole deck — but a beat
            // that silently does nothing is still better than one that hangs.
            await sleep(timing.windows)
            return
        }

        // Make room first: the prompt lifts and the grid's space opens under it. The lift rides the
        // first window's spring rather than getting a beat of its own.
        animate(timing.cardFlight, curve: .spring(response: timing.cardFlight, dampingFraction: 0.85)) {
            self.gridOpen = true
        }

        for index in 0..<count {
            cues.play(CinematicCue.effect(for: .windows))
            animate(timing.cardFlight, curve: .spring(response: timing.cardFlight, dampingFraction: 0.78)) {
                self.settledCards = index + 1
            }
            await sleep(timing.cardStagger)
            if Task.isCancelled { return }
        }

        // The last window is still flying when the loop ends; let it land before beat 6 starts.
        let flown = timing.cardStagger * Double(count)
        await sleep(max(0, timing.windows - flown))
    }

    /// Beat 6. Everything scales toward where the welcome card will be, and the dim lifts.
    private func playRecede() async {
        cues.play(CinematicCue.effect(for: .recede))
        animate(timing.recede) {
            self.receding = true
            self.dim = 0
        }
        await sleep(timing.recede)
    }

    // MARK: Animation

    /// Every mutation the view animates goes through here, so Reduce Motion is applied in one
    /// place: under it, `InkReduceMotion.perform` mutates without a transaction and the state
    /// change is instant — the beat still happens and still holds for `crossFade`, it just does
    /// not travel.
    private func animate(
        _ duration: Double,
        curve: CinematicCurve = .easeOut,
        _ body: () -> Void
    ) {
        InkReduceMotion.perform(curve.animation(duration: duration), body)
    }

    // MARK: Ending

    private func armWatchdog() {
        // Deliberately a real sleep and not the injected seam: the watchdog is a guarantee about
        // wall-clock time, and wiring it to a test's instant clock would make it fire immediately
        // and race the run it exists to protect.
        let deadline = timing.watchdogDeadline
        watchdogTask = Task { [weak self] in
            await CinematicDirector.realSleep(deadline)
            guard !Task.isCancelled else { return }
            await MainActor.run { self?.expire() }
        }
    }

    private func expire() {
        guard let end = sequence.expire() else { return }
        stage = sequence.stage
        ContextLog.error("cinematic stalled in \(end.beat.name); handing off to the card", "onboarding")
        finish(end)
    }

    /// The single exit. Latched, so the four things that can end a run cannot hand off twice.
    private func finish(_ end: CinematicEnd) {
        guard !didFinish else { return }
        didFinish = true

        runTask?.cancel()
        runTask = nil
        watchdogTask?.cancel()
        watchdogTask = nil

        // Never a cut, on any path. An abort mid-beat fades faster than a completed run, which is
        // the difference between "stop" and "that's the end of it".
        cues.stopMusic(fadeOut: end.wasInterrupted ? Self.interruptedFadeOut : Self.completedFadeOut)

        ContextLog.info(
            "cinematic ended \(end.wasInterrupted ? "early" : "complete") after "
                + "\(sequence.visited.map(\.name).joined(separator: "→"))",
            "onboarding")

        let handoff = onFinish
        onFinish = nil
        handoff?(end)
    }

}

/// The two curves the cinematic uses, named so `animate` reads as intent.
enum CinematicCurve {
    case easeOut
    /// `response` is the duration the caller budgeted; the spring is tuned to settle inside it.
    case spring(response: Double, dampingFraction: Double)

    func animation(duration: Double) -> Animation {
        switch self {
        case .easeOut:
            return .easeOut(duration: duration)
        case .spring(let response, let damping):
            return .spring(response: max(0.05, response), dampingFraction: damping, blendDuration: 0)
        }
    }
}
