import Combine
import ContextCore
import Foundation

/// The tutorial's step machine.
///
/// Everything the tutorial claims passes through here, which is why it holds no window, no store and
/// no clock of its own — those arrive as `TutorialEnvironment` closures, so the claims are testable.
///
/// ## The honesty rules this type exists to enforce
///
/// 1. **A frame count is a count of frames.** `collectFrames` leaves only when the store really
///    holds new frames (`TutorialGate.realFrames`). Time passing does not satisfy it, and there is no
///    code path that increments the counter — it is assigned from the store on every poll.
/// 2. **"Found it" needs something found.** `query` leaves only on a real hit from a real search
///    (`.realSearchResult`). An empty result stays on the step and says so.
/// 3. **The Claude payoff cannot be produced by this app.** `claudeProof` leaves only on a
///    `QueryStamp` written strictly after this run began watching (`.genuineToolCall`), which only
///    the MCP server writes, and only when Claude calls a tool.
/// 4. **A waiver is louder than a success.** The two waivable gates set a flag that changes the copy
///    downstream, so a user who skipped past a missing grant is never told their screen is
///    searchable.
/// 5. **Leaving tears everything down.** Both terminal states run the same teardown, so a skip from
///    any step cannot leave the timeline, a coach mark, the spotlight or the music behind.
@MainActor
final class TutorialModel: ObservableObject {

    /// How many frames the collect step waits for.
    ///
    /// Five, because capture runs on a 3 s cadence with a perceptual dedupe gate: a user who really
    /// scrolls produces five distinct screens in about fifteen seconds, and a user who does nothing
    /// produces none however long they sit there. That asymmetry is the point of the step.
    static let frameTarget = 5

    /// Results asked of the store for the search beat. Small on purpose: this is a lesson in how
    /// retrieval feels, not a search UI.
    static let resultLimit = 5

    /// How long a waivable gate waits before it offers a way out. Long enough that a working machine
    /// never sees the escape hatch, short enough that a broken one is not a dead end.
    static let framePatience: Double = 45
    static let grantPatience: Double = 20

    /// The page the tutorial opens.
    ///
    /// Text-dense and unmistakable, which is what the later beats need: the capture pipeline stores a
    /// frame only when the screen has genuinely *changed*, so a page that looks different every time
    /// you scroll is what makes the frame counter move for real, and a page full of words is what
    /// gives OCR something to find again.
    ///
    /// Opened with `NSWorkspace.shared.open` — the user's own default browser, whatever it is — and
    /// **never fetched.** This host answers a scripted request with a bot challenge, so any
    /// reachability probe would report it as down while a real browser loads it perfectly. There is
    /// deliberately no pre-flight check anywhere in this file.
    ///
    /// Nothing downstream assumes a single word from it. If the browser shows an interstitial instead,
    /// the frames are still frames and the counter still counts them; the search beat asks the user
    /// for a word *they* saw rather than testing for one this file guessed.
    static let articleURL = URL(string: "https://www.lingscars.com/")!

    /// The question the handoff puts on the clipboard. Answerable only from captured context, so a
    /// Claude that answers it has genuinely read the store rather than guessed.
    static let suggestedQuestion = "What was I reading about a few minutes ago?"

    /// The chord the timeline really opens on, read from the shortcut layer that registers it rather
    /// than written out here. A tutorial that taught a chord the app does not listen for would be
    /// teaching a surface that does not exist — and the user can rebind it in Settings, after which a
    /// literal string would be wrong for them specifically.
    static var timelineChord: String {
        GlobalShortcuts.shared.display(for: .openTimeline)
    }

    /// Whether that chord is actually live. When it is not — Accessibility not granted, a conflict, a
    /// registration that was refused — the step says the button is what opens the window today instead
    /// of implying the keys will work.
    static var timelineChordIsArmed: Bool {
        GlobalShortcuts.shared.readiness(for: .openTimeline) == .armed
    }

    // MARK: - Published state

    @Published private(set) var step: TutorialStep = .invitation
    /// The steps this run will walk, after dropping any that are already satisfied. Drives the dots.
    @Published private(set) var plan: [TutorialStep] = TutorialStep.flow

    @Published private(set) var framesCollected = 0
    @Published private(set) var didWaiveFrames = false
    @Published private(set) var didWaiveScreenAccess = false

    @Published private(set) var screenIsGranted = false
    @Published private(set) var isRequestingScreenAccess = false

    @Published private(set) var articleDidOpen: Bool?
    /// Whether the timeline window really came up. The step's copy depends on it — describing a
    /// window that is not on screen would be the same class of lie as a fake frame count.
    @Published private(set) var timelineIsOpen = false

    @Published private(set) var results: [TutorialMemory] = []
    @Published private(set) var searchMessage: String?
    @Published private(set) var lastQuery = ""
    @Published private(set) var chosenMemory: TutorialMemory?
    @Published private(set) var chosenMoment: TutorialMoment?

    @Published private(set) var didRestartClaude = false
    @Published private(set) var proof: QueryStamp?

    /// Where the current step's coach mark points, or nil for a card. Republished on every poll so a
    /// window that moved takes its coach mark with it.
    @Published private(set) var targetFrame: CGRect?

    // MARK: - Internals

    private var environment: TutorialEnvironment
    /// When the collect step started watching. Frames are counted strictly from here, so frames the
    /// user captured yesterday cannot satisfy today's lesson.
    private var framesSince: Double = 0
    /// When the handoff began watching for a tool call, snapshotted *before* the user is told to
    /// restart Claude. `QueryStamp.newCall(since:)` is strictly after, so a stamp already on disk
    /// proves nothing.
    private var proofSince: Double = 0
    private var stepEnteredAt: Double = 0
    private var didOpenTimeline = false
    private var hasBegun = false

    init(environment: TutorialEnvironment) {
        self.environment = environment
    }

    // MARK: - Lifecycle

    func begin() {
        guard !hasBegun else { return }
        hasBegun = true
        screenIsGranted = environment.screenIsGranted()
        // Computed once: the plan is what the dots count, and a step count that changed underfoot
        // would make the progress indicator lie in the other direction.
        plan = TutorialStep.flow.filter { !($0 == .screenAccess && screenIsGranted) }
        environment.startMusic()
        enter(.invitation)
    }

    /// Moves on, if the current step's gate allows it. Returns whether it did — the caller is a
    /// button, and a button that silently does nothing is a bug the tests should be able to see.
    @discardableResult
    func advance() -> Bool {
        guard !step.isTerminal, gateIsSatisfied else { return false }
        environment.playClick()
        enter(nextStep())
        return true
    }

    /// Moves past a waivable gate that has *not* been met, recording that it was not met.
    @discardableResult
    func waive() -> Bool {
        guard !step.isTerminal, step.gate.isWaivable, !gateIsSatisfied, waiverIsOffered else {
            return false
        }
        switch step.gate {
        case .realFrames: didWaiveFrames = true
        case .screenRecordingGrant: didWaiveScreenAccess = true
        case .userAction, .realSearchResult, .genuineToolCall: return false
        }
        environment.playClick()
        enter(nextStep())
        return true
    }

    /// Abandons the tutorial from any step. Terminal, and idempotent.
    func skip() {
        guard !step.isTerminal else { return }
        enter(.skipped)
    }

    /// The same teardown the terminal states run, exposed for the window closing under the tutorial's
    /// feet. Abandoning has to be safe from outside the flow too.
    func abandon() {
        skip()
    }

    // MARK: - Gates

    var gateIsSatisfied: Bool {
        switch step.gate {
        case .userAction: return true
        case .screenRecordingGrant: return screenIsGranted
        case .realFrames: return framesCollected >= Self.frameTarget
        case .realSearchResult: return !results.isEmpty
        case .genuineToolCall: return proof != nil
        }
    }

    /// Whether the escape hatch should be visible: only for a waivable gate, only once it has been
    /// unmet for long enough to be a genuine problem rather than a slow start.
    var waiverIsOffered: Bool {
        guard step.gate.isWaivable, !gateIsSatisfied else { return false }
        let patience: Double
        switch step.gate {
        case .realFrames: patience = Self.framePatience
        case .screenRecordingGrant: patience = Self.grantPatience
        case .userAction, .realSearchResult, .genuineToolCall: return false
        }
        return environment.now() - stepEnteredAt >= patience
    }

    // MARK: - Polling

    /// One tick. Called by the controller's timer in the app and directly by tests, which is why
    /// nothing in here sleeps or reads the clock for progress.
    func poll() {
        guard !step.isTerminal else { return }

        // Republished every tick: a coach mark that keeps pointing at where a window *used* to be is
        // the confident arrow aimed at nothing.
        targetFrame = step.target.flatMap { environment.locateTarget($0) }

        switch step {
        case .screenAccess:
            let granted = environment.screenIsGranted()
            guard granted, !screenIsGranted else {
                screenIsGranted = granted
                return
            }
            screenIsGranted = true
            environment.playChime()

        case .collectFrames:
            // Assigned from the store, never incremented. There is deliberately no `+= 1` anywhere
            // in this type: the number on screen is a query result.
            let counted = environment.frameCount(framesSince)
            guard counted != framesCollected else { return }
            let hadEnough = framesCollected >= Self.frameTarget
            framesCollected = counted
            if !hadEnough, counted >= Self.frameTarget { environment.playChime() }

        case .claudeProof:
            guard proof == nil, let stamp = environment.newToolCall(proofSince) else { return }
            proof = stamp
            environment.playChime()

        default:
            break
        }
    }

    // MARK: - Step actions

    /// G3. Asks for the grant the way the rest of the app does, then opens the pane, because the
    /// window server only ever answers "no" to the prompt for Screen Recording.
    func requestScreenAccess() {
        guard !isRequestingScreenAccess else { return }
        isRequestingScreenAccess = true
        Task { [environment] in
            let granted = await environment.requestScreenAccess()
            isRequestingScreenAccess = false
            screenIsGranted = granted || environment.screenIsGranted()
            if !screenIsGranted { environment.openScreenSettings() }
        }
    }

    /// G2, retried by hand when the browser did not open.
    func openArticleAgain() {
        articleDidOpen = environment.openArticle(Self.articleURL)
    }

    /// G9. The real "Search All" button in the real timeline was pressed. Advances only from the step
    /// that asked for it — the button keeps working for the rest of the tutorial and must not skip it.
    func searchPillWasPressed() {
        guard step == .findMoments else { return }
        advance()
    }

    /// G10/G11. A real search of the real store; an empty result is reported, never routed around.
    func search(_ query: String) {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        lastQuery = trimmed
        guard !trimmed.isEmpty else {
            searchMessage = "Type something you were just looking at."
            return
        }
        guard environment.storeIsReadable() else {
            searchMessage = "I can't read the capture store yet, so there is nothing to search."
            return
        }
        let hits = environment.search(trimmed)
        results = hits
        guard !hits.isEmpty else {
            searchMessage = "Nothing captured matches “\(trimmed)” yet. Try a word you actually saw."
            return
        }
        searchMessage = nil
        environment.playChime()
        enter(nextStep())
    }

    /// G12. Tapping the memory goes back to the moment it came from: the real frame captured then,
    /// and — when the shell has wired it — the timeline repositioned on it.
    func choose(_ memory: TutorialMemory) {
        chosenMemory = memory
        chosenMoment = environment.frameNear(memory.at)
        environment.scrubTimeline?(memory.at)
        environment.playClick()
    }

    /// The handoff: put the question somewhere the user can paste it, and restart Claude so it reads
    /// the MCP config it was launched without.
    func handOffToClaude() {
        environment.copyToClipboard(Self.suggestedQuestion)
        didRestartClaude = environment.restartClaude()
        environment.playClick()
    }

    var claudeIsInstalled: Bool { ClaudeRelaunch.isInstalled }

    // MARK: - Copy that depends on what really happened

    /// What the collect step achieved, said either way. This is the sentence a timer-driven counter
    /// would have got wrong.
    var framesSummary: String {
        if framesCollected >= Self.frameTarget {
            return "\(framesCollected) frames landed. That much of your screen is searchable now."
        }
        if didWaiveFrames {
            return framesCollected == 0
                ? "No frames arrived, so there is nothing new to find yet."
                : "Only \(framesCollected) frame\(framesCollected == 1 ? "" : "s") arrived, so there is very little to find yet."
        }
        return "Waiting for frames."
    }

    /// The dots. Terminal states sit past the end of the plan, which is what makes the last dot fill.
    var progress: (index: Int, total: Int) {
        guard let index = plan.firstIndex(of: step) else { return (plan.count, plan.count) }
        return (index, plan.count)
    }

    // MARK: - Transitions

    /// The next step in *this run's* plan, so a step dropped at `begin()` is never walked into.
    private func nextStep() -> TutorialStep {
        guard let index = plan.firstIndex(of: step) else { return step.next ?? .finished }
        let following = index + 1
        return following < plan.count ? plan[following] : .finished
    }

    private func enter(_ next: TutorialStep) {
        step = next
        stepEnteredAt = environment.now()
        // One line per beat. A tutorial that stalls is the kind of thing a user reports as "it just
        // sat there", and the step it sat on is the whole diagnosis.
        ContextLog.info("step \(next.rawValue)", "tutorial")

        switch next {
        case .invitation:
            environment.presentOverlay(next)

        case .article:
            articleDidOpen = environment.openArticle(Self.articleURL)
            environment.playSwoosh()
            environment.presentOverlay(next)

        case .screenAccess:
            screenIsGranted = environment.screenIsGranted()
            environment.presentOverlay(next)

        case .collectFrames:
            framesSince = environment.now()
            framesCollected = 0
            environment.presentOverlay(next)
            // One immediate read so the counter shows a real number rather than a placeholder that
            // happens to be zero.
            poll()

        case .openTimeline:
            environment.presentOverlay(next)

        case .timeline:
            environment.presentTimeline()
            didOpenTimeline = true
            timelineIsOpen = environment.timelineIsVisible()
            environment.playSwoosh()
            environment.presentOverlay(next)
            poll()

        case .scrollBack, .findMoments, .query:
            environment.presentOverlay(next)
            poll()

        case .foundIt:
            environment.presentOverlay(next)
            poll()

        case .claudeHandoff:
            // Before the user is told to restart Claude, so a stamp from an earlier session cannot
            // satisfy the gate that follows.
            proofSince = environment.now()
            environment.presentOverlay(next)

        case .claudeProof:
            environment.presentOverlay(next)
            poll()

        case .allSet:
            environment.playChime()
            environment.presentOverlay(next)

        case .menuBar:
            environment.presentOverlay(next)
            environment.showMenuBarSpotlight()

        case .finished, .skipped:
            tearDown()
        }
    }

    /// Everything this tutorial put on screen, taken back off it. Runs for both terminal states:
    /// finishing and abandoning leave the same empty desktop, and only one of them is a success.
    private func tearDown() {
        environment.dismissOverlay()
        environment.hideMenuBarSpotlight()
        if didOpenTimeline {
            environment.dismissTimeline()
            didOpenTimeline = false
        }
        environment.stopMusic()
        targetFrame = nil
    }
}
