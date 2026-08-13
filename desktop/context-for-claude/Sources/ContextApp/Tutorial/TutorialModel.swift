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
/// 2. **"Found it" needs something found, in the real search panel.** `query` leaves only on a real
///    answer to a real question (`.realSearchResult`), reported by `SearchBarWindow`'s own panel
///    through `SearchPanelEvent`. An empty result stays on the step and says so — and so does the
///    panel merely opening, which reads the newest captures with nothing typed and is not a search.
///    Nothing in this type can run a query; the beat before it does not even take the press that
///    opens the panel, so the surface the user is taught is the one they keep.
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

    /// How long a waivable gate waits before it offers a way out. Long enough that a working machine
    /// never sees the escape hatch, short enough that a broken one is not a dead end.
    static let framePatience: Double = 45
    static let grantPatience: Double = 20
    /// The three beats that wait on the user touching something. Shorter than the frame wait: a user
    /// who is going to press the chord, move their fingers or click the pill does it in the first few
    /// seconds, and one who is not is stuck rather than slow.
    static let hotkeyPatience: Double = 25
    static let dragPatience: Double = 25
    static let searchPanelPatience: Double = 25

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

    /// The chord the Activity window really opens on, read through the environment from the shortcut
    /// layer that registers it rather than written out here. A tutorial that taught a chord the app
    /// does not listen for would be teaching a surface that does not exist — and the user can rebind
    /// it in Settings, after which a literal string would be wrong for them specifically.
    ///
    /// It was `timelineChord`, and the rename is the point rather than tidying: this chord opened the
    /// timeline until Activity became the main window, and a tutorial reading a property named for
    /// the old window is one edit away from teaching the old window again.
    var activityChord: String { environment.activityChord() }

    /// Whether that chord is actually live. When it is not — Accessibility not granted, a conflict, a
    /// registration that was refused — the beat cannot be earned at all, so the way forward is
    /// offered immediately rather than after a wait nothing can end.
    var activityChordIsArmed: Bool { environment.activityChordIsArmed() }

    /// Whether that shortcut is the app's own launch gesture — **both Command keys pressed
    /// together** — rather than a set of keys that is typed.
    ///
    /// Decided from the printed shortcut and from nothing else, which is the same rule
    /// `activityChord` already follows and it matters more here. This beat has two drawings and two
    /// sentences, and picking between them by asking the shortcut layer what *kind* of binding it
    /// holds would put a second copy of "what the app listens for" in the tutorial — one that goes
    /// stale silently the moment somebody rebinds. The string the user is being shown is the only
    /// thing that can be trusted to describe the gesture they have to make; see
    /// `TutorialCommandPair` for what counts as this gesture and why.
    var activityChordIsCommandPair: Bool { TutorialCommandPair.matches(activityChord) }

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

    /// Whether the timeline window really came up when the drag beat asked for it. The step's copy
    /// depends on it — describing a window that is not on screen would be the same class of lie as a
    /// fake frame count, and the shell genuinely declines to open a timeline over an unopened store.
    @Published private(set) var timelineIsOpen = false

    /// Whether the real `openActivity` shortcut really fired while this step was watching for it.
    /// Set from the shortcut layer's own delivery and from nowhere else: there is deliberately no
    /// path in this type that can set it on the tutorial's behalf.
    @Published private(set) var hotkeyFired = false

    /// Whether the user really dragged. Set only by `TutorialDrag` clearing its threshold on real
    /// scroll events; no amount of time on this step moves it.
    @Published private(set) var didDrag = false

    // MARK: The real search panel
    //
    // Every one of these is assigned from a `SearchPanelEvent` the real panel sent and from nowhere
    // else. There is deliberately no search in this type any more: the tutorial cannot produce a
    // result, cannot open a moment, and cannot make its own panel appear — it can only be told.

    /// Whether the real search window is on screen.
    ///
    /// **Not a gate any more, and that is the whole of this beat's regating.** It used to be one —
    /// `findMoments` waited for the panel to appear — which worked while the panel was summoned by
    /// the very press the beat was teaching and closed again the moment it was done. The search
    /// surface is the app's main window now: it is up when the tutorial starts, it is up between
    /// beats, and "is it on screen" is very nearly always true. A gate on it would be satisfied
    /// before the card had finished drawing. What this still answers is the state the *query* beat
    /// needs — the user closed the window and there is nothing to type into (see `speech` and the
    /// "Open search" button `TutorialCardView` grows from it).
    @Published private(set) var searchPanelIsOpen = false

    /// **Whether the user really asked for the search window during this beat.**
    ///
    /// The replacement gate, and the fact the pill beat was always about: pressing "Search All"
    /// brings the main window forward, and `SearchPanelEvent.opened` is that ask being announced.
    /// Reset on the way into the beat, so a window asked for five minutes ago cannot satisfy it —
    /// the same rule `framesSince` applies to frames and `hotkeyFired` to the chord.
    @Published private(set) var searchWasAskedFor = false
    /// Whether the tutorial had to open it because the pill could not. Read by the card, which then
    /// says so rather than congratulating the user on a press they never made.
    @Published private(set) var didWaiveSearchPanel = false
    /// The last question the panel was really asked, trimmed. Empty means it has not been asked one —
    /// the panel reads the newest captures on open with nothing typed, and that read is not a search.
    @Published private(set) var lastQuery = ""
    /// How many moments the panel's last answer to a real question held.
    @Published private(set) var resultCount = 0
    /// Whether one of those results was pressed, and whether a picture of that instant survived.
    /// Nil until one is — "we found things" is not "you went back to one".
    @Published private(set) var openedMomentHasPicture: Bool?

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
        // Recorded because the next beat's card would otherwise say "there it is" about a panel the
        // *tutorial* put on screen, which is a small lie of exactly the kind rule 4 is about.
        case .realSearchPanel: didWaiveSearchPanel = true
        // Nothing recorded for either of these, and deliberately. A waiver flag earns its keep only
        // when a later card would otherwise credit the user with something they did not do, and
        // neither of these has such a card: the drag has no downstream claim at all, and the chord
        // lost its one when the beat after it stopped depending on which window the chord opened —
        // the timeline beat opens its own window on every run now and says so either way. A flag set
        // and never read is the defect this file's rule 4 was written about.
        case .realHotkey, .realGesture: break
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
        case .invitation, .screenAccess, .collectFrames, .openActivity, .timeline, .findMoments,
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
        case .realSearchPanel: return searchWasAskedFor
        // A **question** that came back with something, which is not the same as the panel having
        // rows in it: it opens by reading the newest captures with nothing typed, and that read is
        // the surface introducing itself rather than an answer to anybody. `lastQuery` is only ever
        // non-empty because somebody typed.
        case .realSearchResult: return !lastQuery.isEmpty && resultCount > 0
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
            if !activityChordIsArmed { return true }
            return environment.now() - stepEnteredAt >= Self.hotkeyPatience
        case .realGesture:
            // Nothing on screen to drag. Same reasoning.
            if !timelineIsOpen { return true }
            return environment.now() - stepEnteredAt >= Self.dragPatience
        case .realSearchPanel:
            // No immediate escape here, unlike the two above. Those two can be *known* to be
            // impossible — an unarmed chord cannot fire, a timeline that never opened cannot be
            // dragged — and there is no equivalent fact about a pill. It is drawn in the timeline
            // header whenever the timeline is up, its coach mark degrades to a card when the
            // accessibility tree has not answered yet, and neither of those means the press will
            // fail. So this waits out its patience like an ordinary slow start.
            return environment.now() - stepEnteredAt >= Self.searchPanelPatience
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

    /// Puts the search window back, when the user has closed it on a beat that needs it.
    ///
    /// A button on the card and never automatic, which is the difference between a helpful surface
    /// and one that will not go away: an app that reopens a window on the next poll tick has taken
    /// the close button away from the user. The gate this serves cannot be waived — a "found it" with
    /// nothing behind it is the one claim that would make the rest of the product suspect — so a way
    /// back has to exist, and this is it.
    func openSearchPanel() {
        guard step == .query, !searchPanelIsOpen else { return }
        environment.playClick()
        environment.presentSearchPanel()
        searchPanelIsOpen = environment.searchPanelIsVisible()
    }

    /// The real `openActivity` shortcut fired.
    ///
    /// The window is already up by the time this runs — the shortcut's own handler brought it
    /// forward, which is the entire point of the beat: the user pressed keys and the app appeared
    /// *because they did*. This only records that it happened and moves on, so the keypress is the
    /// transition rather than a button press afterwards congratulating them on it.
    ///
    /// **No swoosh, unlike every other beat that puts something on screen.** That sound means "a
    /// window you did not open has arrived", and it is the wrong claim here: Activity is the app's
    /// main window, it is up before the tutorial starts on almost every run, and the chord brings it
    /// forward rather than conjuring it. The chime — this gate is met — is the honest half.
    func activityHotkeyFired() {
        guard step == .openActivity, !hotkeyFired else { return }
        hotkeyFired = true
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

    /// The real search panel did something. **The only route into this type's search state.**
    ///
    /// This is where the interception used to be. The old shape was `searchPillWasPressed()`: the
    /// shell asked the tutorial before opening its search bar, the tutorial said yes during the beat
    /// that wanted one, and the bar never opened — the user pressed a real control and got a
    /// tutorial-only imitation of results drawn on a coach card. So the surface they were learning to
    /// use was one they would never see again, and the beat's gate was a press rather than an answer.
    ///
    /// The press falls through to the shell now. The bar the user learns to open is opened by their
    /// own click, exactly as it will be forever after — the same principle the timeline beat is built
    /// on — and this is the tutorial finding out what happened afterwards. Nothing in here can put a
    /// panel on screen, run a query, or produce a result.
    ///
    /// Every branch is guarded by the step, because the panel goes on working for the rest of the
    /// tutorial and a stray open during a later beat must not move the flow.
    func searchPanelReported(_ event: SearchPanelEvent) {
        switch event {
        case .opened:
            searchPanelIsOpen = true
            // **The ask, not the window.** `.opened` fires when somebody asks for the search surface
            // — the pill, the chord, the Dock — and that is what the pill beat is waiting for now
            // that the window itself is nearly always up. Recorded whatever the step, because it is a
            // fact about what the user did; the *transition* below is still guarded by the step.
            searchWasAskedFor = true
            // The press *is* the transition, so there is no button afterwards congratulating them on
            // it — the same shape as `activityHotkeyFired`. No "have I already done this" flag is
            // needed and none is kept: `advance()` leaves the step, so a second `.opened` cannot find
            // this branch again.
            guard step == .findMoments else { return }
            environment.playChime()
            advance()

        case .closed:
            searchPanelIsOpen = false

        case .answered(let query, let results):
            // Assigned whatever the step, so the card is never describing an answer that has been
            // replaced. Trimmed by the panel already; kept as it arrived so the two cannot disagree
            // about what was asked.
            lastQuery = query
            let hadAnAnswer = !lastQuery.isEmpty && resultCount > 0
            resultCount = results
            guard step == .query, !hadAnAnswer, !query.isEmpty, results > 0 else { return }
            environment.playChime()

        case .openedMoment(_, let hasPicture):
            guard step == .query, openedMomentHasPicture == nil else { return }
            openedMomentHasPicture = hasPicture
            environment.playChime()
        }
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

        case .openActivity:
            // The chord itself is never spoken — the card shows it as a key chip, because it can
            // contain a digit on a rebound machine and because keys are read, not said.
            //
            // The unarmed line no longer promises to open anything. It used to — the beat after this
            // one needed a window this chord had opened — and the aside said the tutorial would open
            // the timeline itself. Neither half survived the chord moving to Activity: this window is
            // already up, and the timeline beat opens its own. What is left to say is the fact.
            guard activityChordIsArmed else {
                return TutorialSpeech(
                    "I cannot listen for that shortcut.",
                    aside: "Accessibility is off, so those keys will not reach me.")
            }
            // The one gesture in this app that a chip of keycaps cannot spell, so it gets its own
            // sentence as well as its own drawing. "These keys" is a fine thing to say about a chord
            // whose caps are printed beside it and a useless thing to say about two keys that are
            // *identical* and a space bar apart — the reader has to be told which two, and that
            // both go down at once, because the picture and the words are the only two places that
            // can be said. They say it in the same words on purpose: `TutorialCommandPair.spoken` is
            // the label a screen reader gets for the animation.
            // "Your activity" and not "the Activity window": the same words the menu bar's own row
            // uses, so the chord, the row and the card are all naming one thing.
            guard !activityChordIsCommandPair else {
                return TutorialSpeech(
                    "Open your activity.",
                    aside: "Press both Command keys together — the two either side of the space bar.")
            }
            return TutorialSpeech(
                "Open your activity.", aside: "Press these keys, and it will come up.")

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
            //
            // **It names the trackpad, and `TutorialDrag` deliberately does not require one.** That
            // looks like the card asking for something narrower than the gate accepts, and it is —
            // on purpose. The sentence's job is to get a first-time user to make a gesture they have
            // never made on a window they have never seen, and the way to fail at that is to
            // enumerate: "drag, scroll, or swipe" teaches nothing and reads as a manual. So it
            // teaches the one gesture almost every Mac can make, the drawing beside it shows two
            // fingers making it (`TutorialScrollDemo`), and the gate stays wider than the sentence —
            // a mouse wheel satisfies it in silence and nobody is ever told they did it wrong.
            //
            // Reported as: "it isn't clear that they have to swipe on the trackpad with two
            // fingers." The words counted the fingers before; nothing else in the beat did.
            //
            // **One opening line, and it names who opened the window.** There used to be two, chosen
            // by `didWaiveHotkey`: the chord opened the timeline, so the card said "Everything I have
            // seen." when the user's own keypress had put it there and "I opened it for you." when
            // the tutorial had. The chord opens Activity now and this beat opens the timeline on
            // every run, so the second sentence is the only true one and the first would be the beat
            // taking credit for a window nobody summoned.
            return TutorialSpeech(
                "I opened your timeline.",
                aside: "Swipe two fingers across your trackpad to travel through your day.")

        case .findMoments:
            return TutorialSpeech("Now find one moment.", aside: "Click Search All, just up there.")

        case .query:
            // Ordered by what has already happened rather than by what is on screen, and that order
            // matters: pressing a result **closes the panel** — the timeline comes back at that
            // moment, which is the whole payoff — so the "it is not up" sentence below would land on
            // the one user who has just done everything right.
            if let hasPicture = openedMomentHasPicture {
                return TutorialSpeech(
                    "There it is.",
                    aside: hasPicture
                        ? "That is the moment, exactly as it was."
                        : "No picture survived that second — the words are what I still have.")
            }
            if gateIsSatisfied {
                return TutorialSpeech("There it is.", aside: "Click it to go back to that moment.")
            }
            guard searchPanelIsOpen else {
                // The panel was closed with nothing found — Escape, a click elsewhere. The gate is
                // not waivable and there is nothing on screen to satisfy it in, so the card says so
                // and grows the one button that can put it back (`TutorialCardView`). It does not
                // reopen by itself: a window that reappears because you closed it is a window you
                // cannot close.
                return TutorialSpeech(
                    "The search bar is gone.", aside: "Open it again and I will wait for you.")
            }
            if !lastQuery.isEmpty, resultCount == 0 {
                // A real question that really found nothing. Named as such rather than left looking
                // like the beat had not started — the panel says the same thing in its own copy, and
                // a card that kept asking for a first query would be arguing with it.
                return TutorialSpeech(
                    "Nothing matched that.", aside: "Try something you actually looked at.")
            }
            // The instruction points at what the user still has in mind, not at a word they have to
            // dredge up. "A word you saw" reads as a memory test, and it is one they can fail
            // honestly — the store holds minutes, so a word half-remembered from an hour ago finds
            // nothing and the beat lands as the app being broken. What they just looked at is the one
            // thing they cannot get wrong. Reported as: "dont say search a word off the screen, say
            // search something you just looked at."
            let opening =
                didWaiveSearchPanel
                ? "I opened the search bar for you." : "Type something you just looked at."
            return TutorialSpeech(
                opening, aside: "Anything you remember seeing, then press Return.")

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
        environment.stopWatchingActivityHotkey()
        environment.stopWatchingDrag()
        environment.stopWatchingSearchPanel()
        // **Nothing here closes the search window.** It used to, on the way into any beat that did
        // not use it: the panel was the tutorial's own furniture, a floating slab that would have sat
        // over the very window the Claude beats are about, and leaving it up also left the timeline
        // ordered out with nothing to restore it. Both of those facts are gone with the panel. What
        // is left is the app's main window, which the tutorial did not open and does not own: a
        // walkthrough that closed it on the way past would be taking the user's window away from them
        // for reaching the next card.
        //
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

        case .openActivity:
            hotkeyFired = false
            // Armed before the card is on screen, so a user who presses the chord the instant they
            // read it is not racing the watcher.
            environment.watchForActivityHotkey { [weak self] in self?.activityHotkeyFired() }
            environment.presentOverlay(next)

        case .timeline:
            // **The tutorial opens this window, on every run.** It used to open it on one branch
            // only — the chord could not fire and the user took the way out — because the chord
            // itself opened the timeline and the ordinary path was the user's own keypress. The
            // chord opens Activity now, so nothing in the flow before this beat puts a timeline on
            // screen, and a beat that asked somebody to drag through a window that is not there
            // would be teaching a gesture with nowhere to make it.
            //
            // That is a real demotion of this beat and it is the honest one: what the user is being
            // taught here is the *drag*, not the summoning, and the card says who opened the window
            // (see `speech`). `didOpenTimeline` is what hands it back at teardown — the tutorial does
            // not get to leave a window behind that the user never asked for.
            environment.presentTimeline()
            didOpenTimeline = true
            // Assigned from the window rather than from the call: the shell declines to open a
            // timeline over a store that has not finished opening, and the card must not describe a
            // window that is not there. The sound follows the same answer — a swoosh for a window
            // that never arrived is the smallest possible version of the lie this file is about.
            timelineIsOpen = environment.timelineIsVisible()
            if timelineIsOpen { environment.playSwoosh() }
            environment.watchForDrag { [weak self] in self?.dragTravelled() }
            environment.presentOverlay(next)
            poll()

        case .findMoments:
            // Armed before the card is on screen, so a user who reaches straight for the pill is not
            // racing the watcher — the same reason the chord's watcher is armed before its card.
            environment.watchSearchPanel { [weak self] event in
                self?.searchPanelReported(event)
            }
            // **Cleared, not read off the screen.** This beat used to satisfy itself on entry from
            // `searchPanelIsVisible()`, on the reasoning that a beat waiting for something that has
            // already happened never ends. That was right about a summoned panel and is a defect
            // about a main window: the window is up before the tutorial starts and up between every
            // beat, so reading it here would walk straight past the one beat that teaches people
            // where search is. What the beat waits for is the *ask*, and nobody has made one yet.
            searchWasAskedFor = false
            searchPanelIsOpen = environment.searchPanelIsVisible()
            environment.presentOverlay(next)
            poll()

        case .query:
            environment.watchSearchPanel { [weak self] event in
                self?.searchPanelReported(event)
            }
            // The one branch on which the tutorial asks for the window itself: the pill could not be
            // pressed and the user took the way out that says so. Everywhere else it is already up —
            // brought forward by their own click through the shell's own handler, or simply never
            // closed.
            if didWaiveSearchPanel, !environment.searchPanelIsVisible() {
                environment.presentSearchPanel()
                environment.playSwoosh()
            }
            searchPanelIsOpen = environment.searchPanelIsVisible()
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
        environment.stopWatchingActivityHotkey()
        environment.stopWatchingDrag()
        environment.stopWatchingSearchPanel()
        environment.dismissOverlay()
        environment.hideMenuBarSpotlight()
        // The search window is deliberately left where it is. It is the app's main window rather than
        // this run's furniture, and the timeline no longer stands aside for it — the two facts that
        // used to make closing it part of a clean teardown. What the tutorial still takes back is the
        // timeline, and only when the tutorial is what opened it.
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
