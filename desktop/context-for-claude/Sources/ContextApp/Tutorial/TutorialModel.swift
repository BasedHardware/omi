import Combine
import ContextCore
import Foundation

/// The tutorial's step machine.
///
/// Everything the tutorial claims passes through here, which is why it holds no window, no store and
/// no clock of its own — those arrive as `TutorialEnvironment` closures, so the claims are testable.
/// That now includes the *words*: `speech` is the sentence the mark says on each step, computed from
/// what really happened, so "the card never claims something that did not happen" is an assertion a
/// test can make rather than a promise about a `switch` inside a view.
///
/// ## The honesty rules this type exists to enforce
///
/// 1. **The capture beat waits for capture.** `collectFrames` leaves only when the store really holds
///    new frames (`TutorialGate.realFrames`). Time passing does not satisfy it, and there is no code
///    path that increments the count — it is assigned from the store on every poll. The card no
///    longer reads that number out; the gate still holds it.
/// 2. **"Found it" needs something found.** `query` leaves only on a real hit from a real search
///    (`.realSearchResult`). An empty result stays on the step and says so.
/// 3. **The Claude payoff cannot be produced by this app.** `claudeProof` leaves only on a
///    `QueryStamp` written strictly after this run began watching (`.genuineToolCall`), which only
///    the MCP server writes, and only when Claude calls a tool.
/// 4. **A waiver is louder than a success.** The two waivable gates set a flag that changes
///    `outcome`, and `outcome` is the only thing allowed to describe what the capture beat achieved —
///    so a user who skipped past a missing grant is never told their screen is searchable.
/// 5. **Leaving tears everything down.** Both terminal states run the same teardown, so a skip from
///    any step cannot leave the timeline, a coach mark, the spotlight or the music behind.
/// 6. **A beat that asks a question waits for an answer to it.** When a card puts a question to the
///    user, its own replies are the only ways forward: `isAwaitingAnAnswer` holds `gateIsSatisfied`
///    down until one of them has been given. `.userAction` describes a card that has to be read, not
///    one that has to be answered, and the difference is not a detail the view gets to keep — a
///    Continue live over an unanswered question is a third exit that answers nothing, and it landed
///    users on the proof beat having sent Claude no question at all.
@MainActor
final class TutorialModel: ObservableObject {

    /// How many frames the capture beat waits for.
    ///
    /// Five, because capture runs on a 3 s cadence with a perceptual dedupe gate: a user who really
    /// goes and does something produces five distinct screens in about fifteen seconds, and a user
    /// who does nothing produces none however long they sit there. That asymmetry is the point of the
    /// step — and it is the reason the card can stay quiet about the number and still be waiting for
    /// something real.
    static let frameTarget = 5

    /// Results asked of the store for the search beat. Small on purpose: this is a lesson in how
    /// retrieval feels, not a search UI.
    static let resultLimit = 5

    /// How long a waivable gate waits before it offers a way out. Long enough that a working machine
    /// never sees the escape hatch, short enough that a broken one is not a dead end.
    static let framePatience: Double = 45
    static let grantPatience: Double = 20
    /// The two beats that wait on a physical action. Shorter than the frame wait: a user who is going
    /// to press the chord or move their fingers does it in the first few seconds, and one who is not
    /// is stuck rather than slow.
    static let hotkeyPatience: Double = 25
    static let dragPatience: Double = 25

    /// The question the handoff puts on the clipboard. Answerable only from captured context, so a
    /// Claude that answers it has genuinely read the store rather than guessed.
    static let suggestedQuestion = "What was I reading about a few minutes ago?"

    /// The page the capture beat opens for the user to scroll.
    ///
    /// A named constant rather than a literal inside the live environment, so a test can assert
    /// *which* page this beat opens without a browser appearing on the screen of whoever ran the
    /// suite. Anthropic's own site, which is the one page this app may open without choosing a third
    /// party's content for somebody — see `TutorialEnvironment.openPage` for why the beat opens a
    /// page at all after a version of it deliberately did not.
    ///
    /// **The research index rather than the home page, and the reason is the gate.** This beat is
    /// asking for a scroll, and the frames it waits for only exist if there is something under the
    /// scroll to make each screen distinct — the capture path dedupes perceptually, so a short,
    /// mostly-static marketing page can be scrolled to its end and still produce almost nothing. The
    /// research index is a long list of text entries: it is the same host, chosen for the same
    /// reason, and it gives the gesture somewhere to go. Reported as: "open anthropic's research
    /// page, maybe, because there's just more content to read and people can scroll through."
    static let readingMaterial = URL(string: "https://www.anthropic.com/research")!

    /// The chord the timeline really opens on, read through the environment from the shortcut layer
    /// that registers it rather than written out here. A tutorial that taught a chord the app does
    /// not listen for would be teaching a surface that does not exist — and the user can rebind it in
    /// Settings, after which a literal string would be wrong for them specifically.
    var timelineChord: String { environment.timelineChord() }

    /// Whether that chord is actually live. When it is not — Accessibility not granted, a conflict, a
    /// registration that was refused — the beat cannot be earned at all, so the way forward is
    /// offered immediately rather than after a wait nothing can end.
    var timelineChordIsArmed: Bool { environment.timelineChordIsArmed() }

    // MARK: - Published state

    @Published private(set) var step: TutorialStep = .invitation
    /// The steps this run will walk, after dropping any that are already satisfied.
    @Published private(set) var plan: [TutorialStep] = TutorialStep.flow

    /// Frames the store really holds since this step began watching. Read by the gate and by
    /// `outcome`; deliberately never rendered — see `TutorialCardView`.
    @Published private(set) var framesCollected = 0
    @Published private(set) var didWaiveFrames = false
    @Published private(set) var didWaiveScreenAccess = false

    /// Whether the page the capture beat asks the user to scroll really opened. Assigned from
    /// `NSWorkspace`'s own answer and from nowhere else: the card claims it out loud, and a machine
    /// with no browser that could answer the URL gets a different sentence rather than that claim.
    @Published private(set) var didOpenReadingMaterial = false

    @Published private(set) var screenIsGranted = false
    @Published private(set) var isRequestingScreenAccess = false
    /// Whether this run has already put the ask in front of the user. Only ever means "we asked" —
    /// never "they answered", and never "they said yes".
    @Published private(set) var didAskForScreenAccess = false

    /// Whether the timeline window really came up. The step's copy depends on it — describing a
    /// window that is not on screen would be the same class of lie as a fake frame count.
    @Published private(set) var timelineIsOpen = false

    /// Whether the real `openTimeline` shortcut really fired while this step was watching for it.
    /// Set from the shortcut layer's own delivery and from nowhere else: there is deliberately no
    /// path in this type that can set it on the tutorial's behalf.
    @Published private(set) var hotkeyFired = false
    /// Whether the tutorial had to open the timeline itself because the chord could not. Read by the
    /// card, which then says so rather than congratulating the user on a keypress they never made.
    @Published private(set) var didWaiveHotkey = false

    /// Whether the user really dragged. Set only by `TutorialDrag` clearing its threshold on real
    /// scroll events; no amount of time on this step moves it.
    @Published private(set) var didDrag = false

    @Published private(set) var results: [TutorialMemory] = []
    @Published private(set) var searchMessage: String?
    @Published private(set) var lastQuery = ""
    @Published private(set) var chosenMemory: TutorialMemory?
    @Published private(set) var chosenMoment: TutorialMoment?

    /// What really happened when the tutorial handed the first question over. Nil until the answer
    /// comes back — "we asked" is not an outcome and does not get a case.
    @Published private(set) var claudeAsk: TutorialClaudeAsk?
    @Published private(set) var isAskingClaude = false
    /// Whether the Claude that is open was launched before we registered, and so cannot call our
    /// tools until it restarts. When this is true the handoff does **not** run on its own: quitting
    /// an app somebody is in the middle of using is not a thing a tutorial gets to do unasked, so
    /// the card says what it would cost and waits to be told.
    @Published private(set) var claudeNeedsRestart = false
    @Published private(set) var proof: QueryStamp?

    /// Where the current step's coach mark points, or nil for a card. Republished on every poll so a
    /// window that moved takes its coach mark with it.
    @Published private(set) var targetFrame: CGRect?

    /// Where Claude's window is, for the two beats whose card has to stand clear of it. Nil on every
    /// other step and nil whenever it cannot be found — a placement that guessed would park the card
    /// in a space the user is not looking at, which is worse than the middle of the screen.
    @Published private(set) var claudeFrame: CGRect?

    // MARK: - Internals

    private var environment: TutorialEnvironment
    /// When the capture beat started watching. Frames are counted strictly from here, so frames the
    /// user captured yesterday cannot satisfy today's lesson.
    private var framesSince: Double = 0
    /// When the handoff began watching for a tool call, snapshotted *before* the user is told to
    /// restart Claude. `QueryStamp.newCall(since:)` is strictly after, so a stamp already on disk
    /// proves nothing.
    private var proofSince: Double = 0
    private var stepEnteredAt: Double = 0
    private var didOpenTimeline = false
    private var hasBegun = false
    /// Whether the bed this run started is still running. Held so the fade is asked for exactly once
    /// however the run ends: the beat that hands the user to another app stops it (see
    /// `TutorialStep.handsOverToAnotherApp`), and a teardown that follows must not ask for a second
    /// fade on a bed that has already gone.
    private var bedIsPlaying = false

    init(environment: TutorialEnvironment) {
        self.environment = environment
    }

    // MARK: - Lifecycle

    func begin() {
        guard !hasBegun else { return }
        hasBegun = true
        screenIsGranted = environment.screenIsGranted()
        plan = TutorialStep.flow.filter { !($0 == .screenAccess && screenIsGranted) }
        environment.startMusic()
        bedIsPlaying = true
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
        case .realHotkey: didWaiveHotkey = true
        // Nothing recorded, and deliberately: `didWaiveHotkey` exists because a later card would
        // otherwise credit the user with a keypress they never made, and there is no equivalent
        // claim about the drag anywhere downstream to qualify. A flag set and never read is the
        // defect this file's rule 4 was written about.
        case .realGesture: break
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

    /// Whether this beat has put a question to the user and is still waiting to be answered.
    ///
    /// A gate is a fact about the world. This is a fact about the *conversation*, and the two are not
    /// the same thing: `.userAction` means "pressing continue is the whole requirement", which is true
    /// of a card that only has to be read and false of one that has asked something and whose answers
    /// are its own buttons. On such a card Continue is a third exit that answers nothing — and on the
    /// handoff it was the worst kind of third exit, because the beat it leaves for has a gate only
    /// Claude can satisfy and it left having sent Claude nothing.
    ///
    /// Read by `gateIsSatisfied`, so one condition holds both the button's `disabled` and `advance()`.
    /// The view used to carry half of this itself, which is how the other half went missing.
    var isAwaitingAnAnswer: Bool {
        switch step {
        case .claudeHandoff:
            // Two states, one rule. Before the ask: the consent question is on the card and the two
            // replies to it are the two buttons under it. During the ask: we have asked and Claude
            // has not answered, and "we asked" is not an outcome. Once `claudeAsk` is set, an answer
            // really came back — by either route — and the beat is free to be left.
            return isAskingClaude || (claudeAsk == nil && claudeNeedsRestart)
        // Listed rather than defaulted: a beat that starts asking something has to come here and say
        // so, which is the whole reason this is not an `if` inside one card's view.
        case .invitation, .screenAccess, .collectFrames, .openTimeline, .timeline, .findMoments,
            .query, .claudeProof, .allSet, .menuBar, .finished, .skipped:
            return false
        }
    }

    var gateIsSatisfied: Bool {
        // Before the gate, because it is true of any beat that asks: a question the user has not
        // answered is not a requirement the user has met, whatever the step is otherwise waiting on.
        guard !isAwaitingAnAnswer else { return false }
        switch step.gate {
        case .userAction: return true
        case .screenRecordingGrant: return screenIsGranted
        case .realFrames: return framesCollected >= Self.frameTarget
        case .realHotkey: return hotkeyFired
        case .realGesture: return didDrag
        case .realSearchResult: return !results.isEmpty
        case .genuineToolCall: return proof != nil
        }
    }

    /// Whether the escape hatch should be visible: only for a waivable gate, only once it has been
    /// unmet for long enough to be a genuine problem rather than a slow start.
    var waiverIsOffered: Bool {
        guard step.gate.isWaivable, !gateIsSatisfied else { return false }
        switch step.gate {
        case .realFrames:
            // A user who has already declined Screen Recording is not having a slow start. Nothing
            // can arrive for them, this beat knows it, and sitting them out the full patience to be
            // told a fact the tutorial already holds is the flow being stubborn.
            if didWaiveScreenAccess { return true }
            return environment.now() - stepEnteredAt >= Self.framePatience
        case .screenRecordingGrant:
            return environment.now() - stepEnteredAt >= Self.grantPatience
        case .realHotkey:
            // A chord this machine is not listening for can never fire. Making the user wait out a
            // patience for a fact the tutorial already holds is the flow being stubborn — and worse,
            // it is a card teaching keys that do nothing.
            if !timelineChordIsArmed { return true }
            return environment.now() - stepEnteredAt >= Self.hotkeyPatience
        case .realGesture:
            // Nothing on screen to drag. Same reasoning.
            if !timelineIsOpen { return true }
            return environment.now() - stepEnteredAt >= Self.dragPatience
        case .userAction, .realSearchResult, .genuineToolCall:
            return false
        }
    }

    // MARK: - Polling

    /// One tick. Called by the controller's timer in the app and directly by tests, which is why
    /// nothing in here sleeps or reads the clock for progress.
    func poll() {
        guard !step.isTerminal else { return }

        // Republished every tick: a coach mark that keeps pointing at where a window *used* to be is
        // the confident arrow aimed at nothing.
        targetFrame = step.target.flatMap { environment.locateTarget($0) }
        // The same argument, for the window this app does not own. Claude opens *after* the card
        // that talks about it, and the user can move it while they read — so the beat that has to
        // stand clear of it asks every tick rather than once.
        claudeFrame = step.placement == .clearOfClaude ? environment.claudeWindowFrame() : nil

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
            // in this type: the number the gate reads is a query result.
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

    /// Asks for the grant the way the rest of the app does, and then asks the *system* what the
    /// answer was.
    ///
    /// Two things this deliberately does not do, both of which it used to:
    ///
    /// 1. **It does not believe the request.** `CGRequestScreenCaptureAccess` returns before the user
    ///    has touched the dialog, so its answer is evidence that we asked and nothing more. Only
    ///    `screenIsGranted()` — `CGPreflightScreenCaptureAccess` underneath — speaks for the user.
    ///    Letting "we asked" stand in for "they granted" is the same class of lie as a frame counter
    ///    driven by a clock, and it is the one the rest of this file exists to prevent.
    /// 2. **It does not open System Settings itself.** `Permissions.request(.screen)` already opens
    ///    the pane on the branch where the answer is on record, so a second open here made one press
    ///    open two panes — measured 14 ms apart in a live first-run trace, twice in one session.
    ///    The user gets a button for that instead, so one press opens one pane.
    func requestScreenAccess() {
        guard !isRequestingScreenAccess else { return }
        isRequestingScreenAccess = true
        didAskForScreenAccess = true
        Task { [environment] in
            _ = await environment.requestScreenAccess()
            isRequestingScreenAccess = false
            screenIsGranted = environment.screenIsGranted()
        }
    }

    /// The manual way to the pane, for the run where the dialog never appeared because the answer was
    /// already on record. One press, one open.
    func openScreenSettings() {
        environment.openScreenSettings()
    }

    /// The real `openTimeline` shortcut fired.
    ///
    /// The window is already up by the time this runs — the shortcut's own handler opened it, which
    /// is the entire point of the beat: the user pressed keys and a window appeared *because they
    /// did*. This only records that it happened and moves on, so the keypress is the transition
    /// rather than a button press afterwards congratulating them on it.
    ///
    /// It reads `timelineIsVisible()` rather than assuming: the shell declines to open a timeline
    /// over an unopened store, and a card describing a window that is not there is the same class of
    /// lie as a frame count driven by a clock.
    func timelineHotkeyFired() {
        guard step == .openTimeline, !hotkeyFired else { return }
        hotkeyFired = true
        timelineIsOpen = environment.timelineIsVisible()
        if timelineIsOpen {
            didOpenTimeline = true
            environment.playSwoosh()
        }
        environment.playChime()
        advance()
    }

    /// The user really dragged, far enough for it to be a gesture.
    ///
    /// Deliberately does **not** advance. The drag is the lesson, and yanking the card forward
    /// mid-gesture would take the thing they are watching away at the moment it starts moving; the
    /// card changes its line, the chime fires, and Continue becomes pressable.
    func dragTravelled() {
        guard step == .timeline, !didDrag else { return }
        didDrag = true
        environment.playChime()
    }

    /// The real "Search All" button in the real timeline was pressed. Advances only from the step
    /// that asked for it — the button keeps working for the rest of the tutorial and must not skip it.
    ///
    /// - Returns: whether the tutorial took the press. The shell asks, and opens its search bar only
    ///   when the answer is no, so the one real pill serves both without a second window appearing
    ///   over the beat that is using it.
    @discardableResult
    func searchPillWasPressed() -> Bool {
        guard step == .findMoments else { return false }
        return advance()
    }

    /// A real search of the real store; an empty result is reported, never routed around.
    ///
    /// It deliberately does **not** advance. The result *is* the gate, so leaving the step to
    /// `advance()` means the one check that says "there was really a hit" is the one the button runs,
    /// rather than a second copy of that condition written out here.
    func search(_ query: String) {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        lastQuery = trimmed
        chosenMemory = nil
        chosenMoment = nil
        guard !trimmed.isEmpty else {
            results = []
            searchMessage = "Type something you were just looking at."
            return
        }
        guard environment.storeIsReadable() else {
            results = []
            searchMessage = "I can't read the capture store yet, so there is nothing to search."
            return
        }
        let hits = environment.search(trimmed)
        results = hits
        guard !hits.isEmpty else {
            searchMessage = "Nothing captured matches “\(trimmed)” yet. Try something you actually looked at."
            return
        }
        searchMessage = nil
        environment.playChime()
    }

    /// Tapping the memory goes back to the moment it came from: the real frame captured then, and —
    /// when the shell has wired it — the timeline repositioned on it.
    func choose(_ memory: TutorialMemory) {
        chosenMemory = memory
        chosenMoment = environment.frameNear(memory.at)
        environment.scrubTimeline?(memory.at)
        environment.playClick()
    }

    /// The handoff, done rather than described: open Claude and put the question in its prompt.
    ///
    /// The user is not told to ask Claude anything. They watch it happen and then press Return,
    /// which is the one part of it that has to be theirs: a shortcut that can fire by accident must
    /// never send a message on someone's behalf.
    ///
    /// - Parameter restartingFirst: whether they have agreed to Claude being restarted. Only ever
    ///   `true` from the button that says so — `enter(.claudeHandoff)` calls this on its own only on
    ///   the branch where no restart is needed, so nothing here can quit an app unasked. It is also
    ///   ignored downstream when the running Claude turns out not to need one.
    ///
    /// Nothing here decides what happened. `claudeAsk` is assigned from the answer that comes back,
    /// so a machine with no Claude on it lands on an admission rather than on a claim.
    func askClaude(restartingFirst: Bool = false) {
        guard !isAskingClaude else { return }
        isAskingClaude = true
        claudeAsk = nil
        environment.playClick()
        environment.askClaude(Self.suggestedQuestion, restartingFirst) { [weak self] outcome in
            guard let self else { return }
            self.isAskingClaude = false
            self.claudeAsk = outcome
            // Only a branch that genuinely reached a Claude gets the sound that means it worked —
            // which is the pre-filled composer *and* the CLI that was handed the question, but
            // neither of the two clipboard admissions.
            if outcome.didReachClaude { self.environment.playChime() }
        }
    }

    // MARK: - What really happened

    /// What the capture beat achieved. The **only** thing allowed to describe it.
    ///
    /// An enum rather than a sentence because this is the claim the whole tutorial's credibility
    /// rests on: `.caught` is reachable from exactly one condition — the gate's own — and every other
    /// route out of that step lands on an admission. A test can hold this value; it cannot hold a
    /// paragraph.
    var outcome: TutorialOutcome {
        if framesCollected >= Self.frameTarget { return .caught }
        // Checked before the frame waiver, and deliberately: a run that was never allowed to see the
        // screen did not "capture too little", it was blind, and those are different sentences. This
        // is the flag rule 4 promises and the old code set and then never read.
        if didWaiveScreenAccess { return .cannotSee }
        guard didWaiveFrames else { return .waiting }
        return framesCollected == 0 ? .nothingArrived : .tooLittleArrived
    }

    // MARK: - The words

    /// What the mark says on this step, given what really happened.
    ///
    /// One line, one sentence under it, and nothing else — the card has no other copy. Kept here
    /// rather than in the view because these are claims, and a claim belongs where it can be
    /// asserted: `TutorialTests` walks the flow and reads this.
    var speech: TutorialSpeech {
        switch step {
        case .invitation:
            return TutorialSpeech(
                "Let me show you what I do.", aside: "It takes about two minutes.")

        case .screenAccess:
            if screenIsGranted {
                return TutorialSpeech("Thank you.", aside: "Now I can see what you see.")
            }
            // Three states, not two. "We asked" is its own state and says so, because the dialog
            // returns before the user has answered it and a card that jumped straight to thanking
            // them would be reading a grant off our own button press.
            if didAskForScreenAccess {
                return TutorialSpeech(
                    "I am still waiting on that.",
                    aside: "Turn Screen Recording on for me, and I will notice.")
            }
            return TutorialSpeech(
                "I need to see your screen.",
                aside: "Without it there is nothing for me to remember.")

        case .collectFrames:
            // The halves of the honesty rule, said in plain words: while the store has not answered,
            // the mark asks; the moment it has, the mark says so; and if it was never allowed to look
            // at all, it says that instead of asking for something it cannot receive. None of these
            // sentences mentions what is being counted, and none can be reached by a clock.
            switch outcome {
            case .caught:
                return TutorialSpeech("Got it.", aside: "What you were just doing is on your timeline.")
            case .cannotSee:
                return TutorialSpeech(
                    "I still cannot see your screen.",
                    aside: "Nothing will arrive until Screen Recording is on.")
            case .nothingArrived, .tooLittleArrived, .waiting:
                // The ask is a *gesture*, not an act of attention. "Go and look at something" left
                // the user standing at an empty desktop deciding what to look at, and it asked for
                // something this app cannot observe — scrolling is the thing that actually produces
                // distinct screens for the store to hold.
                //
                // Two sentences, because opening the page can fail: a Mac with no handler for an
                // `https` URL is rare and a Mac where the open was refused is not, and the card must
                // not point at a window that never came up.
                guard didOpenReadingMaterial else {
                    return TutorialSpeech(
                        "Open something you would read.",
                        aside: "Then scroll through it for a bit, and I will tell you when I have it.")
                }
                // Named for what it is rather than for the host. "Anthropic's website" was true of
                // the home page this used to open and would be a *vague* description of the research
                // index — the user is being asked to look at a browser window and find the thing the
                // card is talking about, and "research page" is what is written across the top of it.
                return TutorialSpeech(
                    "I opened Anthropic's research page.", stress: "Anthropic",
                    aside: "Scroll through it for a bit, and I will tell you when I have it.")
            }

        case .openTimeline:
            // The chord itself is never spoken — the card shows it as a key chip, because it can
            // contain a digit on a rebound machine and because keys are read, not said.
            guard timelineChordIsArmed else {
                return TutorialSpeech(
                    "I cannot listen for that shortcut.",
                    aside: "Accessibility is off, so I will have to open your timeline myself.")
            }
            return TutorialSpeech(
                "Open your timeline.", aside: "Press these keys, and it will come up.")

        case .timeline:
            guard timelineIsOpen else {
                return TutorialSpeech(
                    "The timeline did not open.",
                    aside: "There is nothing captured for it to show yet.")
            }
            guard !didDrag else {
                return TutorialSpeech(
                    "There you go.", aside: "That is how you get back to anything I saw.")
            }
            // Which way is "back" depends on the user's own scrolling setting, so the card asks for
            // the gesture and not for a direction it cannot promise.
            let opening = didWaiveHotkey ? "I opened it for you." : "Everything I have seen."
            return TutorialSpeech(
                opening, aside: "Drag across it with two fingers to travel through your day.")

        case .findMoments:
            return TutorialSpeech("Now find one moment.", aside: "Click Search All, just up there.")

        case .query:
            guard !results.isEmpty else {
                // The instruction points at what the user still has in mind, not at a word they have
                // to dredge up. "A word you saw" reads as a memory test, and it is one they can fail
                // honestly — the store holds minutes, so a word half-remembered from an hour ago
                // finds nothing and the beat lands as the app being broken. What they just looked at
                // is the one thing they cannot get wrong. Reported as: "dont say search a word off
                // the screen, say search something you just looked at."
                return TutorialSpeech(
                    "Type something you just looked at.",
                    aside: "Anything you remember seeing, then press Return.")
            }
            guard chosenMemory != nil else {
                return TutorialSpeech("There it is.", aside: "Tap it to go back to that moment.")
            }
            return TutorialSpeech(
                "There it is.",
                aside: chosenMoment == nil
                    ? "No picture survived that second — the words are what I still have."
                    : "That is the moment, exactly as it was.")

        case .claudeHandoff:
            // Five answers, and only one of them says a prompt was filled in. "We opened Claude" is
            // not "your question is in Claude", and the difference is the whole beat. The two
            // Terminal answers are separate rather than folded into the app's: the CLI takes the
            // question as an argument, so there is no composer to describe and no Return to ask for.
            switch claudeAsk {
            case .prompted(let restarted, let mayNotReachMe):
                return TutorialSpeech(
                    "Your question is in Claude.", stress: "Claude",
                    aside: {
                        if restarted {
                            return "I restarted it first so it could read me, then typed it in for you."
                        }
                        if mayNotReachMe {
                            return "It is the Claude you already had open, which may not be able to reach me yet."
                        }
                        return "I typed it in for you."
                    }())
            case .ranInTerminal(let handler):
                return TutorialSpeech(
                    "Claude is running in \(handler).", stress: "Claude",
                    aside: "You have it set to Terminal, so I handed your question to the claude command.")
            case .copiedInstead:
                return TutorialSpeech(
                    "Claude would not take it directly.", stress: "Claude",
                    aside: "So I copied your question and brought it forward — paste it in.")
            case .notInstalled:
                return TutorialSpeech(
                    "Claude Desktop is not on this Mac.", stress: "Claude",
                    aside: "I copied your question, ready to paste into the claude command.")
            case .commandNotFound:
                // The mirror of the line above, for the other target: they chose Terminal and there
                // is no claude command here. Naming the right missing thing is the point — sending
                // somebody to install the app they already have would waste their afternoon.
                return TutorialSpeech(
                    "There is no claude command on this Mac.", stress: "claude",
                    aside: "I copied your question, ready to paste in wherever you run it.")
            case nil:
                // The consent beat. It names the cost before it offers the button, because the cost
                // is somebody else's open conversation.
                guard !claudeNeedsRestart else {
                    return TutorialSpeech(
                        "Claude is open already.", stress: "Claude",
                        aside: "It has not read me yet, and it only reads me when it starts. May I close and reopen it?")
                }
                return TutorialSpeech(
                    "Let me ask Claude for you.", stress: "Claude",
                    aside: "Opening it with your question already typed in.")
            }

        case .claudeProof:
            guard let proof else {
                switch claudeAsk {
                case .prompted(_, let mayNotReachMe):
                    // A Claude that never re-read our config may never call a tool, and this gate
                    // cannot be waived — so the card names the way out instead of waiting silently.
                    guard !mayNotReachMe else {
                        return TutorialSpeech(
                            "Send it in Claude.", stress: "Claude",
                            aside: "It is in the prompt. If nothing reaches me, quitting and reopening Claude is what fixes it.")
                    }
                    return TutorialSpeech(
                        "Send it in Claude.", stress: "Claude",
                        aside: "It is already in the prompt — press Return there, and I will notice.")
                case .ranInTerminal:
                    // Nothing to press. The CLI was launched with the question as its argument, so
                    // asking for a Return here would be asking for a keystroke that has no job.
                    return TutorialSpeech(
                        "Claude is answering in your terminal.", stress: "Claude",
                        aside: "I will only say this worked once Claude has really called me.")
                case .copiedInstead, .notInstalled, .commandNotFound:
                    return TutorialSpeech(
                        "Paste it into Claude.", stress: "Claude",
                        aside: "I will only say this worked once Claude has really called me.")
                case nil:
                    return TutorialSpeech(
                        "Ask Claude your question.", stress: "Claude",
                        aside: "I will only say this worked once Claude has really called me.")
                }
            }
            return TutorialSpeech(
                "Claude just read your context.", stress: "Claude",
                aside: "It called \(proof.tool), and the server that served it wrote that down.")

        case .allSet:
            return TutorialSpeech("That is everything.", aside: outcome.sentence)

        case .menuBar:
            return TutorialSpeech("I am up here.", aside: "Click me whenever you want me.")

        case .finished, .skipped:
            return TutorialSpeech("")
        }
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
        // Every watcher this flow can install is torn down here and re-armed by the step that wants
        // it. One place, so a beat cannot leave a system-wide event monitor running behind it — and
        // so no watcher can outlive the step whose gate it feeds.
        environment.stopWatchingTimelineHotkey()
        environment.stopWatchingDrag()
        // The bed's last beat, decided by the step rather than by a timer — see
        // `TutorialStep.handsOverToAnotherApp`. Here rather than in `tearDown` because the run's end
        // is not something the tutorial gets to schedule: the proof beat waits on Claude and can wait
        // a very long time. `stopTheBed` is idempotent, so the later beats that are also handovers
        // change nothing.
        if next.handsOverToAnotherApp { stopTheBed() }
        // One line per beat. A tutorial that stalls is the kind of thing a user reports as "it just
        // sat there", and the step it sat on is the whole diagnosis.
        ContextLog.info("step \(next.rawValue)", "tutorial")

        switch next {
        case .invitation:
            environment.presentOverlay(next)

        case .screenAccess:
            screenIsGranted = environment.screenIsGranted()
            environment.presentOverlay(next)

        case .collectFrames:
            framesSince = environment.now()
            framesCollected = 0
            environment.presentOverlay(next)
            // After the card, not before it. `openPage` brings the browser forward, and a browser
            // that arrives last is the window the user's next scroll lands in — which is the whole
            // ask of this beat. The card floats above it either way.
            //
            // Assigned, never assumed: the sentence on the card is a claim about something the user
            // can check by looking at their Dock.
            //
            // Not opened at all for someone who declined the screen grant. Nothing they scroll can
            // be captured, this beat already knows it and says so, and putting a page on the screen
            // of somebody who just told this app not to look at their screen is the tutorial taking
            // something for its own benefit.
            if !didWaiveScreenAccess {
                didOpenReadingMaterial = environment.openPage(Self.readingMaterial)
                // The sound the timeline gets when it arrives, for the same reason: something the
                // user did not open themselves has appeared on their screen. Only on the branch
                // where it really did.
                if didOpenReadingMaterial { environment.playSwoosh() }
            }
            // One immediate read, so the gate starts from the store's answer rather than from a
            // placeholder that happens to be zero.
            poll()

        case .openTimeline:
            hotkeyFired = false
            // Armed before the card is on screen, so a user who presses the chord the instant they
            // read it is not racing the watcher.
            environment.watchForTimelineHotkey { [weak self] in self?.timelineHotkeyFired() }
            environment.presentOverlay(next)

        case .timeline:
            // The window is normally already up — the user's own keypress opened it through the
            // shortcut's own handler. The tutorial opens it itself on exactly one branch: the chord
            // could not fire and the user took the way out that says so.
            if didWaiveHotkey {
                environment.presentTimeline()
                didOpenTimeline = true
                environment.playSwoosh()
            }
            timelineIsOpen = environment.timelineIsVisible()
            environment.watchForDrag { [weak self] in self?.dragTravelled() }
            environment.presentOverlay(next)
            poll()

        case .findMoments, .query:
            environment.presentOverlay(next)
            poll()

        case .claudeHandoff:
            // Before Claude is restarted, so a stamp from the session we are about to end cannot
            // satisfy the gate that follows.
            proofSince = environment.now()
            claudeNeedsRestart = environment.claudeRestartIsNeeded()
            environment.presentOverlay(next)
            // Only the branch with no destructive side effect runs by itself. When a restart really
            // is needed the card asks first — see `claudeNeedsRestart`.
            if !claudeNeedsRestart { askClaude() }

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
        environment.stopWatchingTimelineHotkey()
        environment.stopWatchingDrag()
        environment.dismissOverlay()
        environment.hideMenuBarSpotlight()
        if didOpenTimeline {
            environment.dismissTimeline()
            didOpenTimeline = false
        }
        // Idempotent, and it has to be: on every run that got as far as the browser the bed was
        // already faded out by the step that opened it, and a second `stopMusic()` here would ask
        // the audio layer for a fade on a bed that is not playing.
        stopTheBed()
        targetFrame = nil
        claudeFrame = nil
    }

    /// Fades the bed out, once.
    private func stopTheBed() {
        guard bedIsPlaying else { return }
        bedIsPlaying = false
        environment.stopMusic()
    }
}

// MARK: - What the capture beat achieved

/// The result of the one beat that can genuinely fail, as a value.
///
/// The sentences live on the enum rather than in the view for the same reason the enum exists: there
/// is exactly one route to `.caught`, so there is exactly one route to the sentence that says the
/// screen is searchable.
enum TutorialOutcome: Equatable, Sendable {
    /// Frames genuinely landed while the step was watching.
    case caught
    /// The step was left with nothing at all in the store.
    case nothingArrived
    /// The step was left with something, but less than the beat asked for.
    case tooLittleArrived
    /// The screen grant was declined, so nothing could ever have arrived. Distinct from
    /// `nothingArrived` because the reason is the thing worth saying.
    case cannotSee
    /// Still watching. Not reachable from the closing card — the capture beat is either met or
    /// waived before it — and it resolves to an admission anyway, because a state that should not
    /// happen must not be the one that claims success.
    case waiting

    var sentence: String {
        switch self {
        case .caught: return "What you were doing is searchable now, and Claude can read it."
        case .cannotSee: return "You have kept Screen Recording off, so I saw none of it."
        case .nothingArrived: return "Nothing arrived while I was watching, so there is nothing new to find."
        case .tooLittleArrived: return "Very little arrived, so there is not much to find yet."
        case .waiting: return "I am not sure anything arrived, so there may be nothing new to find."
        }
    }
}

// MARK: - The mark's line

/// One card's worth of copy: the line the mark speaks, and at most one sentence under it.
///
/// `stress` is a *substring of* `lead` rather than a second copy of those words, so a run the mark
/// leans on can never drift out of the sentence it belongs to — the emphasis is a lookup, not a
/// parallel string a careless edit could leave behind.
struct TutorialSpeech: Equatable {
    let lead: String
    let stress: String?
    let aside: String?

    init(_ lead: String, stress: String? = nil, aside: String? = nil) {
        self.lead = lead
        self.stress = stress
        self.aside = aside
    }

    /// `lead`, cut into the runs a talking mark wants: plain, the stressed run, plain.
    var runs: [(String, Emphasis)] {
        guard let stress, let range = lead.range(of: stress) else { return [(lead, .plain)] }
        let before = String(lead[lead.startIndex..<range.lowerBound])
        let after = String(lead[range.upperBound...])
        return [(before, .plain), (stress, .bold), (after, .plain)].filter { !$0.0.isEmpty }
    }

    /// Everything this card says out loud, as one string. What a test reads.
    var everythingSaid: String { [lead, aside].compactMap { $0 }.joined(separator: " ") }
}
