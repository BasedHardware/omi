import AppKit
import ContextCore

/// One real memory, as the tutorial shows it.
///
/// A projection of `Hit` rather than the hit itself: the card needs a time, a line of text, and the
/// app it came from, and carrying the whole wire shape into the view would invite the view to grow a
/// dependency on fields the tutorial has no business rendering.
struct TutorialMemory: Identifiable, Equatable, Sendable {
    var id: Double { at }
    /// Unix epoch seconds — the exact moment, which is what "jump back to it" means.
    let at: Double
    let when: String
    let text: String
    let app: String?
    /// "said", "heard", or "screen", straight from the hit.
    let kind: String

    init(_ hit: Hit) {
        at = hit.at
        when = hit.when
        text = hit.text
        app = hit.app
        kind = hit.kind
    }

    init(at: Double, when: String, text: String, app: String?, kind: String) {
        self.at = at
        self.when = when
        self.text = text
        self.app = app
        self.kind = kind
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
    /// Nothing on this Mac answers `claude://` links, so the question went on the clipboard and
    /// Claude was brought forward. A pre-fill was *not* achieved and the card must not imply one.
    case copiedInstead
    /// Claude Desktop is not installed. The question is on the clipboard for the CLI.
    case notInstalled

    /// Whether a prompt really got filled in. The one condition allowed to sound like success.
    var didPrefill: Bool {
        if case .prompted = self { return true }
        return false
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

    /// Opens Claude with a question already typed into its prompt, and answers what really happened.
    ///
    /// The tutorial opens nothing else. It used to launch a text-dense stranger's website to have
    /// something to capture, which put a third party's page on the screen of someone who had just
    /// been asked to let this app watch their screen — and taught the product on content that was not
    /// theirs. The capture beat now runs on whatever they already have open, which is both the more
    /// honest demonstration and the more convincing one.
    ///
    /// Asynchronous because the honest version of this can have a wait in it: a Claude the user has
    /// agreed to restart takes a moment to go.
    ///
    /// The `Bool` is the user's answer to "may I restart it first", asked by the card and never
    /// assumed here. It is ignored when no running Claude needs one.
    var askClaude: (String, Bool, @escaping (TutorialClaudeAsk) -> Void) -> Void = { _, _, answer in
        answer(.notInstalled)
    }

    /// Whether a Claude is open that was launched before our MCP config was written, and so cannot
    /// call our tools until it restarts. The one question the card has to ask before it may offer to
    /// quit an app the user is using.
    var claudeRestartIsNeeded: () -> Bool = { false }

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

        environment.search = { query in
            guard let store, !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return []
            }
            let hits = (try? Queries.recall(store, query: query, limit: TutorialModel.resultLimit)) ?? []
            return hits.map(TutorialMemory.init)
        }

        environment.frameNear = { instant in
            guard let store else { return nil }
            // A window around the moment rather than the whole day: this is called on a tap and only
            // ever needs the nearest frame, so it reads seconds instead of hours.
            let span: Double = 120
            let frames = (try? RewindQueries.frames(
                store, since: instant - span, until: instant + span)) ?? []
            guard let index = frames.nearestIndex(to: instant) else { return nil }
            let frame = frames[index]
            return TutorialMoment(
                at: frame.capturedAt, app: frame.appName, windowTitle: frame.windowTitle,
                imagePath: frame.imagePath)
        }

        environment.screenIsGranted = { Permissions.check(.screen) }
        environment.requestScreenAccess = { await Permissions.request(.screen) }
        environment.openScreenSettings = { Permissions.openSettings(for: .screen) }

        environment.askClaude = { question, restartingFirst, answer in
            ClaudeHandoff.ask(question, restartingFirst: restartingFirst, then: answer)
        }
        environment.claudeRestartIsNeeded = { ClaudeHandoff.restartIsNeeded() }

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
/// The prompt is **pre-filled, not sent**: `ClaudeRouter` opens `claude://claude.ai/new?q=…`, which
/// lands the question in the composer of a *normal new chat* with the user still holding the Return
/// key. That is the reused mechanism, not a second one — the search bar routes through the same
/// `ClaudeRouter`, only asking for its own surface. Every failure is then reported as itself: no
/// handler for the scheme is the clipboard branch, no Claude at all is its own branch, and neither is
/// allowed to come back looking like a pre-fill.
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
/// 1. **A restart is only ever *needed* on evidence** — `restartIsNeeded(launchedAt:registeredAt:)`,
///    which is `launchDate <= claudeDesktopRegisteredAt` and nothing else. A Claude launched after
///    we wrote already has us. A missing date on either side is not evidence, and answers false:
///    this must never quit an app because it could not tell.
/// 2. **Even when it is needed, the user decides.** `ask` takes `restartingFirst` from the card, and
///    the card only offers it after saying what it would do. Declining hands the question over to
///    the Claude they already have and says the reach may be stale — which is a better outcome than
///    quitting their session to force a gate. The gate itself is unfakeable either way.
///
/// And what comes back describes what *happened*, never what was attempted: a Claude that refuses to
/// quit — which any app with unsaved state may — reports `restarted: false`.
@MainActor
enum ClaudeHandoff {

    /// Where the tutorial's question goes: a normal new chat on Claude's home surface.
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
        var isInstalled: @MainActor () -> Bool
        var running: @MainActor () -> [RunningClaude]
        /// When our registration was last written, from `ClaudeRegistrar`.
        var registeredAt: @MainActor () -> Date?
        var route: @MainActor (String) -> Result<ClaudeRouter.Delivery, ClaudeRouter.RouteError>
        var copyToClipboard: @MainActor (String) -> Void
        /// Waits for the Claudes it is given to actually go, then calls back on the main actor.
        ///
        /// Takes the processes rather than re-querying, so it waits on exactly the ones that were
        /// asked to quit: a Claude we deliberately spared must not hold this open for its full
        /// timeout. A seam so a test never sleeps — the live one polls for ten seconds, a test's
        /// answers at once.
        var waitForExit: @MainActor ([RunningClaude], @escaping @MainActor () -> Void) -> Void

        @MainActor
        static func live() -> Probe {
            Probe(
                isInstalled: { ClaudeRelaunch.isInstalled },
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
                route: { ClaudeRouter.route($0, to: .claudeApp, surface: surface) },
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

    /// Whether any Claude on this Mac right now is one a restart would genuinely help.
    ///
    /// `probe` is optional rather than defaulted to `.live()` because a default argument is
    /// evaluated in the *caller's* isolation, and building the live probe needs the main actor.
    static func restartIsNeeded(probe injected: Probe? = nil) -> Bool {
        let probe = injected ?? .live()
        let registeredAt = probe.registeredAt()
        return probe.running().contains {
            restartIsNeeded(launchedAt: $0.launchedAt, registeredAt: registeredAt)
        }
    }

    // MARK: - The handoff

    /// - Parameter restartingFirst: whether the user has agreed to a restart. Ignored when no
    ///   running Claude needs one, so consent can never be turned into a quit that was pointless.
    static func ask(
        _ question: String,
        restartingFirst: Bool,
        probe injected: Probe? = nil,
        then answer: @escaping (TutorialClaudeAsk) -> Void
    ) {
        let probe = injected ?? .live()
        guard probe.isInstalled() else {
            probe.copyToClipboard(question)
            ContextLog.info("no Claude Desktop; the question went to the clipboard", "tutorial")
            answer(.notInstalled)
            return
        }

        let registeredAt = probe.registeredAt()
        let running = probe.running()
        let stale = running.filter {
            restartIsNeeded(launchedAt: $0.launchedAt, registeredAt: registeredAt)
        }

        guard !stale.isEmpty else {
            // Nothing here a restart would help: either no Claude is running, or the one that is
            // was launched after we registered and already has us. Terminating would cost the user
            // their session and buy nothing.
            deliver(question, restarted: false, mayNotReachMe: false, probe: probe, then: answer)
            return
        }

        guard restartingFirst else {
            // They said no. Their Claude keeps its conversation, the question still goes in, and the
            // card says the reach may be stale rather than pretending otherwise.
            ContextLog.info("handing over without the restart the user declined", "tutorial")
            deliver(question, restarted: false, mayNotReachMe: true, probe: probe, then: answer)
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
                question, restarted: quit, mayNotReachMe: !quit, probe: probe, then: answer)
        }
    }

    private static func deliver(
        _ question: String,
        restarted: Bool,
        mayNotReachMe: Bool,
        probe: Probe,
        then answer: @escaping (TutorialClaudeAsk) -> Void
    ) {
        switch probe.route(question) {
        case .success(let delivery):
            switch delivery.mechanism {
            case .prefilledTab:
                answer(.prompted(restarted: restarted, mayNotReachMe: mayNotReachMe))
            case .clipboard, .terminal:
                // `.terminal` is unreachable for `.claudeApp` and is folded in rather than crashed
                // on: either way the question is somewhere to paste from, which is what the card
                // has to say.
                answer(.copiedInstead)
            }
        case .failure(let error):
            probe.copyToClipboard(question)
            ContextLog.error("could not hand the question to Claude: \(error.sentence)", "tutorial")
            answer(.notInstalled)
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
