import AppKit
import ContextCore

/// One real memory, as the tutorial shows it.
///
/// A projection of `Hit` rather than the hit itself: the card needs a time, a line of text, the app
/// it came from and the picture that was on screen, and carrying the whole wire shape into the view
/// would invite the view to grow a dependency on fields the tutorial has no business rendering.
///
/// **`text` is not a title and never was.** `Queries.screenText` fills it with the window's
/// accessibility dump, or failing that its OCR, truncated — which for a browser is every string the
/// chrome exposes, in layout order: *"tab Close Tab New Tab Search Tabs Update …"*. Setting that as
/// the headline of a result is how this beat came to be reported as "this list with only text looks
/// so bland": a run of interface soup, an app name, and a wire-format timestamp. So the window title
/// travels alongside it (`window`, straight off the hit — nothing here parses or trims), `title` is
/// derived from that the way the real search panel derives its own, and `text` stays exactly what it
/// is: the words the hit matched on, which the card shows *inside* the well when there is no picture
/// and hands to VoiceOver in full.
struct TutorialMemory: Identifiable, Equatable, Sendable {
    var id: Double { at }
    /// Unix epoch seconds — the exact moment, which is what "jump back to it" means.
    let at: Double
    let when: String
    let text: String
    let app: String?
    /// The window's own title, when the capture recorded one. Nil for speech, which was not in a
    /// window, and for a frame whose owner announced nothing.
    let window: String?
    /// "said", "heard", or "screen", straight from the hit.
    let kind: String
    /// The frame that was really captured at this moment, for the card's picture.
    ///
    /// Resolved once, at search time, by the same nearest-frame lookup `frameNear` uses — see
    /// `TutorialEnvironment.live`. Nil is an ordinary outcome and never an error: speech was never on
    /// screen, retention unlinks files, and a machine can genuinely have no frame within reach of the
    /// instant a spoken line landed on.
    let frame: RewindFrame?

    init(_ hit: Hit, frame: RewindFrame? = nil) {
        at = hit.at
        when = hit.when
        text = hit.text
        app = hit.app
        window = hit.window
        kind = hit.kind
        self.frame = frame
    }

    init(
        at: Double, when: String, text: String, app: String?, kind: String,
        window: String? = nil, frame: RewindFrame? = nil
    ) {
        self.at = at
        self.when = when
        self.text = text
        self.app = app
        self.window = window
        self.kind = kind
        self.frame = frame
    }

    /// Whether this was something seen rather than something said. The one question the card's well
    /// and its glyph both turn on.
    var isScreen: Bool { kind == "screen" }

    /// The card's headline — a short, clean line, never the matched text.
    ///
    /// `SearchSource.title` and `SearchSpeech.title` rather than a second opinion about either: the
    /// real results panel answers this question for the same two kinds of row, and a tutorial that
    /// named them differently would be teaching a surface the user is about to leave.
    var title: String {
        guard isScreen else {
            return SearchSpeech.title(for: kind == "said" ? .mic : .system)
        }
        let derived = SearchSource.title(appName: app ?? "", windowTitle: window)
        // Neither a title nor an app — nothing was recorded about the window at all. The matched
        // words are then the only true thing left to head the card with.
        return derived.isEmpty ? text : derived
    }

    /// The line under the title: the site the window was showing, the app that owned it, or that
    /// this was a conversation.
    var source: String {
        guard isScreen else { return app ?? SearchSpeech.unplacedSource }
        let derived = SearchSource.source(appName: app ?? "", windowTitle: window)
        return derived.isEmpty ? RewindQueries.unknownApp : derived
    }
}

/// A frame that was really captured at a moment, for the "jump back" beat.
struct TutorialMoment: Equatable, Sendable {
    let at: Double
    let app: String
    let windowTitle: String?
    let imagePath: String
}

/// What actually happened when the tutorial handed the first question to Claude.
///
/// A value rather than a sentence, for the same reason `TutorialOutcome` is: the card is only
/// allowed to say "your question is in Claude" on the one branch where a prompt was genuinely
/// pre-filled, and a test can hold this where it cannot hold a paragraph. Nothing here is reachable
/// by the tutorial *asking* — every case is the answer that came back.
///
/// Two families, because there are two targets: `Settings → Agents → Claude target` chooses between
/// the Claude app and the `claude` CLI, and what "it worked" looks like is genuinely different on
/// each. The app pre-fills a composer and waits for the user's Return; the CLI takes the question as
/// an argument and is already running with it. Collapsing those into one case would put the app
/// branch's "press Return there" in front of somebody whose question has already been sent.
enum TutorialClaudeAsk: Equatable, Sendable {
    /// Claude opened with the question already in its prompt, waiting for the user to send it.
    ///
    /// - Parameters:
    ///   - restarted: whether it was genuinely relaunched first, so it has read our MCP config.
    ///     False when no restart was needed *and* when one was attempted and refused — this records
    ///     what happened, never what was asked for.
    ///   - mayNotReachMe: whether this is a Claude that was already running from before we
    ///     registered, so it may not be able to call our tools at all. True when the user declined
    ///     the restart, and true when the app would not quit. The card has to say so, because the
    ///     proof beat can then wait on something that will never arrive.
    case prompted(restarted: Bool, mayNotReachMe: Bool)
    /// The `claude` CLI was launched with the question, in whichever app this Mac opens `.command`
    /// files with — `handler` is that app's name, so the card can point at the window that just
    /// appeared rather than at a generic "Terminal" the user may not run.
    ///
    /// There is no `restarted`/`mayNotReachMe` pair here, and that is not an omission: a CLI process
    /// is new every time and reads `~/.claude.json` as it starts, so it can never be the stale-config
    /// case those two flags exist to describe.
    case ranInTerminal(handler: String)
    /// Nothing on this Mac answers `claude://` links, so the question went on the clipboard and
    /// Claude was brought forward. A pre-fill was *not* achieved and the card must not imply one.
    case copiedInstead
    /// Claude Desktop is not installed. The question is on the clipboard for the CLI.
    case notInstalled
    /// The Terminal target was chosen and there is no `claude` command on this Mac to run. The
    /// question is on the clipboard. Distinct from `notInstalled` because the two say to install
    /// different things, and a card that named the wrong one would send somebody to the wrong page.
    case commandNotFound

    /// Whether a prompt really got filled in. The one condition allowed to sound like success.
    var didPrefill: Bool {
        if case .prompted = self { return true }
        return false
    }

    /// Whether the question genuinely reached a Claude — the condition for the sound that means it
    /// worked.
    ///
    /// Wider than `didPrefill` on purpose. The CLI branch fills no composer, and that is the point of
    /// it: the question was handed straight to a running `claude`, which is at least as much of an
    /// arrival as a pre-fill. What stays outside is the three clipboard admissions, where nothing
    /// reached anything.
    var didReachClaude: Bool {
        switch self {
        case .prompted, .ranInTerminal: return true
        case .copiedInstead, .notInstalled, .commandNotFound: return false
        }
    }
}

/// Every side effect the tutorial has, behind a closure.
///
/// The step machine is the part that has to be provably honest, so it owns no `NSWindow`, no store,
/// no clock and no audio: it asks this. `live` wires the real ones; tests wire counters and stubs
/// and can therefore assert the things that matter — that the frame counter reflects the store and
/// not elapsed time, that the payoff cannot fire without a genuine stamp, and that abandoning tears
/// every overlay down.
@MainActor
struct TutorialEnvironment {
    // MARK: Time

    var now: () -> Double = { ContextTime.now }

    /// How often the model is polled. `nil` means "nobody polls automatically" — the shape tests
    /// use, so a test never waits on wall-clock time.
    var pollInterval: Double? = 1.0

    // MARK: The store

    /// Showable frames captured since an instant. The whole of G5's honesty: this is a count from
    /// the capture database, so a step waiting on it cannot be satisfied by a timer.
    var frameCount: (Double) -> Int = { _ in 0 }

    /// A real full-text search of the real store.
    var search: (String) -> [TutorialMemory] = { _ in [] }

    /// The frame nearest an instant, so tapping a memory lands on the picture that was really taken
    /// then rather than on an approximation of it.
    var frameNear: (Double) -> TutorialMoment? = { _ in nil }

    /// Whether the store could be opened at all. False on a fresh install, where the honest thing to
    /// say is that there is nothing to count yet.
    var storeIsReadable: () -> Bool = { false }

    // MARK: Permissions

    var screenIsGranted: () -> Bool = { false }
    var requestScreenAccess: () async -> Bool = { false }
    var openScreenSettings: () -> Void = {}

    // MARK: The world outside

    /// Opens a URL in whatever the user's default browser is, and answers whether it really opened.
    ///
    /// The `Bool` is the whole reason this is not a `-> Void`. The capture beat's card says "I opened
    /// Anthropic's research page" — a claim about something the user can look up by glancing at their
    /// Dock — and a card that says it while `NSWorkspace` answered false is the same class of lie as
    /// a frame count driven by a clock. The model records what came back and the copy follows it.
    ///
    /// This is the *only* page the tutorial opens, and it took an argument to earn its way back. An
    /// earlier version launched a text-dense **stranger's** website to have something to capture,
    /// which put a third party's page on the screen of someone who had just been asked to let this
    /// app watch their screen. What replaced it — "go and look at something of your own" — was worse
    /// on the machine that matters: a first run is a fresh Mac with an empty desktop, and the beat
    /// sat there waiting for frames the user had nothing to generate. `anthropic.com` is the one
    /// host this app can open without choosing somebody else's content for them, and
    /// `TutorialModel.readingMaterial` names the page on it that the beat's gate can actually be
    /// satisfied from.
    var openPage: (URL) -> Bool = { _ in false }

    /// Hands a question to Claude, and answers what really happened.
    ///
    /// *Which* Claude is not a parameter here on purpose: the live implementation reads
    /// `Settings → Agents → Claude target` at the moment of the handoff, and this seam exists so a
    /// test can stub the whole act rather than to give the tutorial a second opinion about where the
    /// question should go. Both targets come back through the same `TutorialClaudeAsk`.
    ///
    /// Asynchronous because the honest version of this can have a wait in it: a Claude the user has
    /// agreed to restart takes a moment to go.
    ///
    /// The `Bool` is the user's answer to "may I restart it first", asked by the card and never
    /// assumed here. It is ignored when no running Claude needs one, and on the Terminal target,
    /// where no restart is ever needed.
    var askClaude: (String, Bool, @escaping (TutorialClaudeAsk) -> Void) -> Void = { _, _, answer in
        answer(.notInstalled)
    }

    /// Whether a Claude is open that was launched before our MCP config was written, and so cannot
    /// call our tools until it restarts. The one question the card has to ask before it may offer to
    /// quit an app the user is using. Answers false whenever the chosen target is the CLI, which
    /// never has a stale config to restart out of.
    var claudeRestartIsNeeded: () -> Bool = { false }

    /// Where Claude's own window is right now, in AppKit screen coordinates, or nil when there is
    /// none on screen. Read every tick for the two beats that have to stand clear of it — Claude
    /// opens *after* the card does, and the user can move it while they read.
    var claudeWindowFrame: () -> CGRect? = { nil }

    // MARK: Our own windows

    /// Opens the timeline **on the tutorial's behalf**, which is only ever the honest fallback for a
    /// machine whose chord cannot fire. The ordinary route is the user pressing the shortcut, which
    /// the app's own handler answers — see `watchForTimelineHotkey`.
    var presentTimeline: () -> Void = {}
    var dismissTimeline: () -> Void = {}
    var timelineIsVisible: () -> Bool = { false }

    /// The chord the timeline really opens on, and whether this machine is genuinely listening for
    /// it. Both read from the shortcut layer that registers it: a tutorial that taught a chord the
    /// app does not listen for would be teaching a surface that is not there, and the user can
    /// rebind it, after which a literal string would be wrong for them specifically.
    var timelineChord: () -> String = { "" }
    var timelineChordIsArmed: () -> Bool = { false }

    /// Watches for the real `openTimeline` shortcut firing, calling back when it does. The window it
    /// opens is opened by the app's own handler; this only ever *observes*, which is what keeps the
    /// beat's gate a fact about the user rather than about the tutorial.
    var watchForTimelineHotkey: (@escaping () -> Void) -> Void = { _ in }
    var stopWatchingTimelineHotkey: () -> Void = {}

    /// Watches for a real drag over this app's own windows, calling back once the user has genuinely
    /// travelled far enough for it to be a gesture rather than a twitch.
    var watchForDrag: (@escaping () -> Void) -> Void = { _ in }
    var stopWatchingDrag: () -> Void = {}
    /// Repositions the real timeline on a moment. `nil` when the shell has not wired one, which is
    /// the state on a build where nothing has connected the tutorial to the timeline's model — the
    /// beat still runs, and still shows the real captured frame, it just does not move the track.
    var scrubTimeline: ((Double) -> Void)?

    /// Where a real piece of UI actually is, in AppKit screen coordinates. `nil` degrades the coach
    /// mark to a card.
    var locateTarget: (TutorialTarget) -> CGRect? = { _ in nil }

    /// Shows/hides the coach mark for a step. Called on every step change and on every reposition,
    /// so a step that lost its target stops pointing at where it used to be.
    var presentOverlay: (TutorialStep) -> Void = { _ in }
    var dismissOverlay: () -> Void = {}

    var showMenuBarSpotlight: () -> Void = {}
    var hideMenuBarSpotlight: () -> Void = {}

    // MARK: Proof

    /// A tool call served strictly after `since`, or nil.
    var newToolCall: (Double) -> QueryStamp? = { _ in nil }

    // MARK: Sound

    var playClick: () -> Void = {}
    var playSwoosh: () -> Void = {}
    var playChime: () -> Void = {}
    var startMusic: () -> Void = {}
    var stopMusic: () -> Void = {}

    /// The real one. `store` is the app's capture database, opened read-only by the caller when the
    /// app's own writer is not reachable from here.
    static func live(store: ContextStore?) -> TutorialEnvironment {
        var environment = TutorialEnvironment()

        environment.storeIsReadable = { store != nil }

        environment.frameCount = { since in
            guard let store else { return 0 }
            // `until` is now rather than `.infinity`: a frame stamped in the future is a clock fault,
            // and counting it would let one bad row satisfy the gate this exists to hold.
            return (try? RewindQueries.frameCount(store, since: since, until: ContextTime.now)) ?? 0
        }

        /// The frame really captured nearest an instant, or nil.
        ///
        /// One implementation with two callers, and they have to be one: the grid shows a picture per
        /// result and tapping one says "that is the moment, exactly as it was". Two lookups with two
        /// windows could disagree — a card showing one frame while the sentence under it was written
        /// about another — which is precisely the class of claim this whole flow is built not to make.
        ///
        /// A window around the moment rather than the whole day: only the nearest frame is ever
        /// wanted, so it reads seconds instead of hours.
        func nearestFrame(to instant: Double) -> RewindFrame? {
            guard let store else { return nil }
            let span: Double = 120
            let frames =
                (try? RewindQueries.frames(
                    store, since: instant - span, until: instant + span)) ?? []
            guard let index = frames.nearestIndex(to: instant) else { return nil }
            return frames[index]
        }

        environment.search = { query in
            guard let store, !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return []
            }
            let hits = (try? Queries.recall(store, query: query, limit: TutorialModel.resultLimit)) ?? []
            // The picture is fetched here, once per result, rather than in the card: a `body` that
            // reads the database is a database read on every re-publish, and the beat re-publishes on
            // every poll tick. `resultLimit` is four, so this is four bounded window reads per Return
            // — and only for the kind of hit that can have a picture at all. Speech was never on
            // screen, and looking for a frame near it here would put whatever happened to be in front
            // of the user under somebody's sentence.
            return hits.map { hit in
                TutorialMemory(hit, frame: hit.kind == "screen" ? nearestFrame(to: hit.at) : nil)
            }
        }

        environment.frameNear = { instant in
            guard let frame = nearestFrame(to: instant) else { return nil }
            return TutorialMoment(
                at: frame.capturedAt, app: frame.appName, windowTitle: frame.windowTitle,
                imagePath: frame.imagePath)
        }

        environment.screenIsGranted = { Permissions.check(.screen) }
        environment.requestScreenAccess = { await Permissions.request(.screen) }
        environment.openScreenSettings = { Permissions.openSettings(for: .screen) }

        environment.openPage = { NSWorkspace.shared.open($0) }

        // Both of these read `Settings → Agents → Claude target` inside `ClaudeHandoff`, on the call
        // rather than here, so a target changed while the card is up is the target the next attempt
        // uses. Nothing in this file caches it — see `ClaudeHandoff` on the preference's one home.
        environment.askClaude = { question, restartingFirst, answer in
            ClaudeHandoff.ask(question, restartingFirst: restartingFirst, then: answer)
        }
        environment.claudeRestartIsNeeded = { ClaudeHandoff.restartIsNeeded() }
        environment.claudeWindowFrame = { ClaudeWindowProbe.frame() }

        // The honest fallback only, for the machine where the chord cannot fire. Wired exactly as
        // the shell wires it (`ContextApp.swift`) so the window the tutorial has to open is the same
        // window, with the same buttons behind it, as the one the shortcut opens.
        environment.presentTimeline = {
            guard let store else { return }
            RewindWindow.present(
                store: store,
                onOpenSettings: { SettingsWindow.present() },
                onSearch: { query in
                    guard !Tutorial.searchPillWasPressed() else { return }
                    SearchBarWindow.present(prefill: query)
                })
        }
        environment.dismissTimeline = { RewindWindow.dismiss() }
        environment.timelineIsVisible = { RewindWindow.isVisible }
        environment.timelineChord = { GlobalShortcuts.shared.display(for: .openTimeline) }
        environment.timelineChordIsArmed = {
            GlobalShortcuts.shared.readiness(for: .openTimeline) == .armed
        }
        environment.watchForTimelineHotkey = { fired in TutorialHotkeyWatch.start(fired) }
        environment.stopWatchingTimelineHotkey = { TutorialHotkeyWatch.stop() }
        environment.watchForDrag = { travelled in TutorialDragWatcher.shared.start(travelled) }
        environment.stopWatchingDrag = { TutorialDragWatcher.shared.stop() }
        environment.locateTarget = { TutorialTargetLocator.frame(of: $0) }

        environment.showMenuBarSpotlight = { MenuBarSpotlight.show() }
        environment.hideMenuBarSpotlight = { MenuBarSpotlight.hide() }

        environment.newToolCall = { QueryStamp.newCall(since: $0) }

        environment.playClick = { Sound.effect(.click) }
        environment.playSwoosh = { Sound.effect(.swoosh) }
        environment.playChime = { Sound.effect(.chime) }
        environment.startMusic = { Sound.music.start() }
        environment.stopMusic = { Sound.music.stop() }

        return environment
    }
}

// MARK: - The shortcut

/// Observes the real `openTimeline` shortcut for the length of one step.
///
/// A thin wrapper over `GlobalShortcuts.addObserver` so the token has somewhere to live and a second
/// `start` cannot leak the first. It deliberately owns no window: the chord's own handler opens the
/// timeline, and this only reports that it fired.
@MainActor
enum TutorialHotkeyWatch {
    private static var token: UUID?

    static func start(_ fired: @escaping () -> Void) {
        stop()
        token = GlobalShortcuts.shared.addObserver { action in
            guard action == .openTimeline else { return }
            fired()
        }
    }

    static func stop() {
        if let token { GlobalShortcuts.shared.removeObserver(token) }
        token = nil
    }
}

// MARK: - Claude

/// Puts the tutorial's first question into Claude, rather than telling the user to type it.
///
/// On the default target the prompt is **pre-filled, not sent**: `ClaudeRouter` opens
/// `claude://claude.ai/new?q=…`, which lands the question in the composer of a *normal new chat* with
/// the user still holding the Return key. That is the reused mechanism, not a second one — this type
/// owns no routing of its own, it only decides what to ask `ClaudeRouter` for. Every failure is then
/// reported as itself: no handler for the scheme is the clipboard branch, no Claude at all is its own
/// branch, and neither is allowed to come back looking like a pre-fill.
///
/// ## The target is the user's, and this is where it is read
///
/// `Settings → Agents → Claude target` chooses between the Claude app and the `claude` CLI, and this
/// handoff is its consumer. The preference lives in exactly one place — `SettingsStore.claudeTarget`,
/// the only owner and only writer of `context.settings.claudeTarget` — and is read *here*, at the
/// moment of the handoff, rather than captured when the tutorial's environment was built. A second
/// copy on `ClaudeRouter` is deliberately not reintroduced: a preference with two homes is a
/// preference that disagrees with itself, and the version of this app that had one shipped a dropdown
/// nothing read.
///
/// ## The surface is a decision, not an inherited default
///
/// This beat is teaching somebody to *ask a question about their own screen*, and the answer comes
/// from an MCP server `ClaudeRegistrar` writes into **both** of Claude's configs. So either surface
/// could answer — but only one of them is where a person asks a question. Shipping the search bar's
/// `claude://code/new` here dropped the user into the Code tab mid-tutorial, which is why `surface`
/// is now named at this call site instead of being whatever the router happened to hard-code.
///
/// ## Quitting the user's Claude is not something this gets to decide
///
/// Claude reads its MCP config at startup, so a Claude that was open *before* we registered cannot
/// call our tools. That justifies a restart — but it is a **conditional** justification, and the
/// first version of this file did not test the condition: it terminated any running Claude, which
/// could take a conversation the user was in the middle of and give nothing back for it.
///
/// So there are two rules, and both are about evidence:
///
/// 1. **A restart is only ever *needed* on evidence** — `restartIsNeeded(launchedAt:registeredAt:
///    serverIsLoaded:)`. The strongest evidence is a live server process: `ClaudeServerLiveness`
///    looks for one belonging to the running Claude, and what it finds settles the question either
///    way, because it is the thing the user actually cares about rather than a proxy for it. Only
///    when it cannot tell does this fall back to `launchDate <= claudeDesktopRegisteredAt`, on the
///    reasoning that a Claude launched after we wrote already read us. A missing date on either side
///    is not evidence, and answers false: this must never quit an app because it could not tell.
/// 2. **Even when it is needed, the user decides.** `ask` takes `restartingFirst` from the card, and
///    the card only offers it after saying what it would do. Declining hands the question over to
///    the Claude they already have and says the reach may be stale — which is a better outcome than
///    quitting their session to force a gate. The gate itself is unfakeable either way.
///
/// And what comes back describes what *happened*, never what was attempted: a Claude that refuses to
/// quit — which any app with unsaved state may — reports `restarted: false`.
@MainActor
enum ClaudeHandoff {

    /// Where the tutorial's question goes *in the Claude app*: a normal new chat on Claude's home
    /// surface. Ignored by the Terminal target, whose CLI is its own surface.
    ///
    /// Named, and a stored constant rather than a literal inside `Probe.live`, so the choice is a
    /// thing a test can read without opening a URL — asserting this by launching Claude would mean
    /// taking over the screen of whoever ran the suite.
    static let surface = ClaudeRouter.Surface.chat

    /// One running Claude, reduced to what the decision needs.
    ///
    /// A value with closures rather than the `NSRunningApplication` itself, so a test can assert the
    /// thing that actually matters here: that `terminate` was **not** called.
    struct RunningClaude {
        var launchedAt: Date?
        var terminate: () -> Void
        var hasQuit: () -> Bool

        init(launchedAt: Date?, terminate: @escaping () -> Void, hasQuit: @escaping () -> Bool) {
            self.launchedAt = launchedAt
            self.terminate = terminate
            self.hasQuit = hasQuit
        }
    }

    /// Everything outside this type that the handoff reads or acts on.
    ///
    /// Every closure is `@MainActor`: a nested type does not inherit the enclosing `@MainActor`, and
    /// each of these reaches for something — `NSWorkspace`, `NSPasteboard`, `ClaudeRouter` — that is
    /// isolated to it.
    struct Probe {
        /// Claude **Desktop** specifically, which is what the `.claudeApp` target needs and what the
        /// restart decision is about. Named for the app rather than for "Claude" so the Terminal
        /// path's skipping of it reads as deliberate: a Mac with the `claude` CLI and no desktop app
        /// is a perfectly good machine for that target.
        var desktopIsInstalled: @MainActor () -> Bool
        var running: @MainActor () -> [RunningClaude]
        /// When our registration was last written, from `ClaudeRegistrar`.
        var registeredAt: @MainActor () -> Date?
        /// The one routing call. Takes the target so there is a single path to `ClaudeRouter` rather
        /// than one per target, and so a test can assert *which* target the preference produced.
        var route:
            @MainActor (String, ClaudeRouter.Target) -> Result<ClaudeRouter.Delivery, ClaudeRouter.RouteError>
        var copyToClipboard: @MainActor (String) -> Void
        /// Waits for the Claudes it is given to actually go, then calls back on the main actor.
        ///
        /// Takes the processes rather than re-querying, so it waits on exactly the ones that were
        /// asked to quit: a Claude we deliberately spared must not hold this open for its full
        /// timeout. A seam so a test never sleeps — the live one polls for ten seconds, a test's
        /// answers at once.
        var waitForExit: @MainActor ([RunningClaude], @escaping @MainActor () -> Void) -> Void
        /// Whether a server of ours is alive inside the Claude Desktop that is running now.
        ///
        /// The evidence the date comparison cannot supply. Declared last and defaulted to `.unknown`
        /// so the tests that predate it keep exercising the date path they were written for — and
        /// `.unknown` is the honest default anyway: a `Probe` nobody wired this into has not looked.
        var serverIsLoaded: @MainActor () -> ClaudeServerLiveness.State = { .unknown }

        @MainActor
        static func live() -> Probe {
            Probe(
                desktopIsInstalled: { ClaudeRelaunch.isInstalled },
                running: {
                    NSRunningApplication.runningApplications(
                        withBundleIdentifier: ClaudeRelaunch.bundleIdentifier
                    ).map { application in
                        RunningClaude(
                            launchedAt: application.launchDate,
                            terminate: { application.terminate() },
                            hasQuit: { application.isTerminated })
                    }
                },
                registeredAt: { ClaudeRegistrar.claudeDesktopRegisteredAt },
                // `surface` is the chat surface this beat asks for and is ignored by `.terminal`,
                // which has no URL to build.
                route: { question, target in
                    ClaudeRouter.route(question, to: target, surface: surface)
                },
                copyToClipboard: { text in
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(text, forType: .string)
                },
                waitForExit: { quitting, done in
                    Task {
                        // Bounded: ten seconds in quarter-second steps. A Claude that refuses to
                        // quit is the user's decision to make, and the handoff reports that rather
                        // than waiting on it forever.
                        for _ in 0..<40 {
                            if quitting.allSatisfy({ $0.hasQuit() }) { break }
                            try? await Task.sleep(for: .milliseconds(250))
                        }
                        done()
                    }
                },
                serverIsLoaded: {
                    ClaudeServerLiveness.state(
                        claudeDesktopPIDs: Set(
                            NSRunningApplication.runningApplications(
                                withBundleIdentifier: ClaudeRelaunch.bundleIdentifier
                            ).map(\.processIdentifier)))
                })
        }
    }

    // MARK: - The decision

    /// Whether a running Claude has to be restarted before it can call our tools.
    ///
    /// Pure, and both nils answer false. "I could not read a launch date" and "nothing is registered
    /// on disk" are both *absence of evidence*, and neither is a licence to quit an app somebody is
    /// using — a Claude with no entry for us would not gain one by relaunching anyway.
    static func restartIsNeeded(launchedAt: Date?, registeredAt: Date?) -> Bool {
        guard let launchedAt, let registeredAt else { return false }
        return launchedAt <= registeredAt
    }

    /// The same decision, once a live server has been looked for.
    ///
    /// **The regression this exists for.** The date comparison above is a *proxy*: it asks whether
    /// Claude started before we wrote the config, and infers the tools from that. The inference is
    /// only sound while a server that was spawned stays spawned, and it does not. Claude starts its
    /// MCP servers once and does not respawn one that dies, so replacing the app bundle — an update,
    /// a reinstall, a rebuild — leaves a Claude that launched *after* the registration with no tools
    /// at all. Every question this file asked answered "fine": the entry was on disk, the launch date
    /// was later than the write. The tutorial handed its payoff question to that Claude, and Claude
    /// told the user it had no access to what they had been reading.
    ///
    /// So a real observation of a running server outranks the proxy in **both** directions. It says
    /// no restart is needed when the tools are demonstrably there — which the date test also gets
    /// wrong the other way, every time we rewrite the config behind a Claude that is already serving
    /// us — and it says a restart *is* needed when they are demonstrably not, which is the case the
    /// proxy cannot see at all. `.unknown` changes nothing and falls back, because a probe that could
    /// not look is not a reason to start quitting applications.
    static func restartIsNeeded(
        launchedAt: Date?,
        registeredAt: Date?,
        serverIsLoaded: ClaudeServerLiveness.State
    ) -> Bool {
        switch serverIsLoaded {
        case .servingClaudeDesktop: return false
        case .notServingClaudeDesktop: return true
        case .unknown: return restartIsNeeded(launchedAt: launchedAt, registeredAt: registeredAt)
        }
    }

    /// Whether any Claude on this Mac right now is one a restart would genuinely help, for the target
    /// the user has actually chosen. The card's consent question hangs off this.
    ///
    /// `settings` and `probe` are optional rather than defaulted to `.shared`/`.live()` because a
    /// default argument is evaluated in the *caller's* isolation, and both of those need the main
    /// actor.
    static func restartIsNeeded(settings: SettingsStore? = nil, probe: Probe? = nil) -> Bool {
        restartIsNeeded(for: (settings ?? .shared).claudeTarget, probe: probe)
    }

    /// - Parameter target: the Terminal target always answers false, and that is a fact about the
    ///   CLI rather than a shortcut. `claude` is a new process on every invocation and reads
    ///   `~/.claude.json` as it starts, so it cannot be the "launched before we registered" case at
    ///   all. Offering to quit somebody's Claude Desktop to fix a CLI that was never broken would be
    ///   the exact trade this type exists to refuse: a real cost for nothing.
    static func restartIsNeeded(for target: ClaudeRouter.Target, probe injected: Probe? = nil) -> Bool {
        guard target == .claudeApp else { return false }
        let probe = injected ?? .live()
        let registeredAt = probe.registeredAt()
        // Read once and shared across the running Claudes: the answer is about this Mac's process
        // table, not about any one of them, and probing per-process would let two Claudes in the
        // same list disagree about a fact neither of them owns.
        let serverIsLoaded = probe.serverIsLoaded()
        return probe.running().contains {
            restartIsNeeded(
                launchedAt: $0.launchedAt, registeredAt: registeredAt, serverIsLoaded: serverIsLoaded)
        }
    }

    // MARK: - The handoff

    /// The handoff, to whichever Claude the user chose in Settings.
    ///
    /// This overload exists so that "read the preference" is a step with a name that a test can call:
    /// the defect it replaces was a hard-coded `.claudeApp` here, which left the Settings dropdown
    /// writing a key nothing read. `settings` is injectable for exactly that test and defaults to the
    /// one real store.
    ///
    /// - Parameter restartingFirst: whether the user has agreed to a restart. Ignored when no
    ///   running Claude needs one, so consent can never be turned into a quit that was pointless.
    static func ask(
        _ question: String,
        restartingFirst: Bool,
        settings: SettingsStore? = nil,
        probe: Probe? = nil,
        then answer: @escaping (TutorialClaudeAsk) -> Void
    ) {
        ask(
            question, to: (settings ?? .shared).claudeTarget, restartingFirst: restartingFirst,
            probe: probe, then: answer)
    }

    /// - Parameters:
    ///   - target: where the question goes. Named rather than assumed — see the type's note on the
    ///     preference having exactly one home.
    ///   - restartingFirst: whether the user has agreed to a restart. Ignored when no running Claude
    ///     needs one, so consent can never be turned into a quit that was pointless.
    static func ask(
        _ question: String,
        to target: ClaudeRouter.Target,
        restartingFirst: Bool,
        probe injected: Probe? = nil,
        then answer: @escaping (TutorialClaudeAsk) -> Void
    ) {
        let probe = injected ?? .live()

        guard target == .claudeApp else {
            // The Terminal target skips every question below it, and each skip is its own fact. The
            // `claude` CLI does not need Claude Desktop installed; it reads `~/.claude.json` fresh on
            // every launch, so there is no stale config for a restart to fix; and so `restartingFirst`
            // is deliberately unused here rather than passed along. Quitting an app the user is in
            // the middle of, to help a process that has not started yet, would be a cost with no
            // purchase. What can still fail — no `claude` on this Mac — fails inside `deliver`, on
            // `ClaudeRouter`'s own answer rather than on a second guess at it.
            deliver(
                question, to: target, restarted: false, mayNotReachMe: false, probe: probe,
                then: answer)
            return
        }

        guard probe.desktopIsInstalled() else {
            probe.copyToClipboard(question)
            ContextLog.info("no Claude Desktop; the question went to the clipboard", "tutorial")
            answer(.notInstalled)
            return
        }

        let registeredAt = probe.registeredAt()
        let running = probe.running()
        let serverIsLoaded = probe.serverIsLoaded()
        let stale = running.filter {
            restartIsNeeded(
                launchedAt: $0.launchedAt, registeredAt: registeredAt, serverIsLoaded: serverIsLoaded)
        }

        guard !stale.isEmpty else {
            // Nothing here a restart would help: either no Claude is running, or the one that is
            // was launched after we registered and already has us. Terminating would cost the user
            // their session and buy nothing.
            deliver(
                question, to: target, restarted: false, mayNotReachMe: false, probe: probe,
                then: answer)
            return
        }

        guard restartingFirst else {
            // They said no. Their Claude keeps its conversation, the question still goes in, and the
            // card says the reach may be stale rather than pretending otherwise.
            ContextLog.info("handing over without the restart the user declined", "tutorial")
            deliver(
                question, to: target, restarted: false, mayNotReachMe: true, probe: probe,
                then: answer)
            return
        }

        for claude in stale { claude.terminate() }
        probe.waitForExit(stale) {
            // What happened, not what was asked for. `terminate` is a request an app with unsaved
            // state may refuse, and a Claude still running is a Claude that never re-read anything.
            let quit = stale.allSatisfy { $0.hasQuit() }
            if !quit {
                ContextLog.info("Claude did not quit; handing over to the process still running", "tutorial")
            }
            deliver(
                question, to: target, restarted: quit, mayNotReachMe: !quit, probe: probe,
                then: answer)
        }
    }

    /// The single call into `ClaudeRouter`, and the one place a delivery becomes a sentence the card
    /// is allowed to say.
    ///
    /// The answer is switched off the *mechanism* that came back rather than off the target that was
    /// asked for, because those are different claims: asking for the app and getting the clipboard is
    /// a real outcome, and it is the one the router reports when nothing on the Mac answers
    /// `claude://`. `restarted`/`mayNotReachMe` only reach the `.prompted` case, which is the only
    /// case they describe.
    private static func deliver(
        _ question: String,
        to target: ClaudeRouter.Target,
        restarted: Bool,
        mayNotReachMe: Bool,
        probe: Probe,
        then answer: @escaping (TutorialClaudeAsk) -> Void
    ) {
        switch probe.route(question, target) {
        case .success(let delivery):
            switch delivery.mechanism {
            case .prefilledTab:
                answer(.prompted(restarted: restarted, mayNotReachMe: mayNotReachMe))
            case .terminal(_, let handler):
                answer(.ranInTerminal(handler: handler))
            case .clipboard:
                answer(.copiedInstead)
            }
        case .failure(let error):
            probe.copyToClipboard(question)
            ContextLog.error("could not hand the question to Claude: \(error.sentence)", "tutorial")
            // Which thing is missing decides which sentence the card gets: a Mac with no `claude`
            // command and a Mac with no Claude Desktop need to be told to install different things.
            answer(target == .terminal ? .commandNotFound : .notInstalled)
        }
    }
}

/// Which app on this Mac is Claude Desktop.
///
/// All that is left of a `ClaudeRelaunch` that used to terminate and relaunch on its own. The
/// relaunch now belongs to `ClaudeHandoff`, because restarting Claude and *then not handing it the
/// question* was the shape of the beat the user objected to: it left them looking at a freshly
/// opened Claude and a card telling them to type something.
@MainActor
enum ClaudeRelaunch {
    static let bundleIdentifier = "com.anthropic.claudefordesktop"

    static var isInstalled: Bool {
        NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleIdentifier) != nil
    }
}

// MARK: - Where Claude is on screen

/// Claude's own window, so the tutorial's card can stand beside it instead of on top of it.
///
/// `CGWindowListCopyWindowInfo` rather than the Accessibility API, for the same reason
/// `SettingsWindowProbe` uses it: since 10.15 only `kCGWindowName` is gated behind Screen
/// Recording — bounds, owner and layer are not — so this answers on a machine that has granted this
/// app nothing at all. Nothing here reads a *name*, and nothing here needs one.
///
/// Every branch can answer nil and the caller has to live with it: Claude may not be running, may
/// have no window yet (the handoff has only just launched it), or may be on a display that has since
/// gone away. A placement that invents a rectangle when it cannot find one would park the card in a
/// space the user is not looking at, which is worse than the middle of the screen.
@MainActor
enum ClaudeWindowProbe {

    /// The largest ordinary window belonging to Claude, in AppKit screen coordinates.
    ///
    /// Largest rather than frontmost, and layer 0 only: an app's tooltips, its own panels and its
    /// menu-bar extras all appear in the same listing, and the window the user is reading is the big
    /// one. A pane the card is asked to stand clear of has to be the pane, not a popover on it.
    static func frame() -> CGRect? {
        let pids = Set(
            NSRunningApplication.runningApplications(
                withBundleIdentifier: ClaudeRelaunch.bundleIdentifier
            ).map(\.processIdentifier))
        guard !pids.isEmpty else { return nil }
        guard
            let listing = CGWindowListCopyWindowInfo(
                [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
        else { return nil }

        var best: CGRect?
        for window in listing {
            guard let pid = window[kCGWindowOwnerPID as String] as? pid_t, pids.contains(pid),
                (window[kCGWindowLayer as String] as? Int) == 0,
                let raw = window[kCGWindowBounds as String] as? NSDictionary,
                let bounds = CGRect(dictionaryRepresentation: raw)
            else { continue }
            // A collapsed entry is a window nobody is reading; treating one as the pane would send
            // the card to stand beside a point.
            guard bounds.width > 200, bounds.height > 200 else { continue }
            if best == nil || bounds.width * bounds.height > best!.width * best!.height {
                best = bounds
            }
        }
        // The listing is in global CoreGraphics coordinates and the card is placed with
        // `NSWindow.setFrame`, which is not the same space. `ScreenSpace` owns that flip for the
        // whole app — a second copy of it here is how an overlay ends up on the wrong monitor.
        return best.flatMap { ScreenSpace.live.appKit(from: $0) }
    }
}
