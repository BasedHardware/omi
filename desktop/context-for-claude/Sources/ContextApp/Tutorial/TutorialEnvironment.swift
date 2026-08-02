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

    /// Opens the article in the default browser. False if nothing could be opened, which the step
    /// then says out loud instead of pretending.
    var openArticle: (URL) -> Bool = { _ in false }
    var copyToClipboard: (String) -> Void = { _ in }
    /// Relaunches Claude Desktop. False when it is not installed, which is a normal state — plenty of
    /// people only use the CLI.
    var restartClaude: () -> Bool = { false }

    // MARK: Our own windows

    var presentTimeline: () -> Void = {}
    var dismissTimeline: () -> Void = {}
    var timelineIsVisible: () -> Bool = { false }
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

        environment.openArticle = { url in NSWorkspace.shared.open(url) }
        environment.copyToClipboard = { text in
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
        }
        environment.restartClaude = { ClaudeRelaunch.perform() }

        environment.presentTimeline = {
            guard let store else { return }
            RewindWindow.present(store: store)
        }
        environment.dismissTimeline = { RewindWindow.dismiss() }
        environment.timelineIsVisible = { RewindWindow.isVisible }
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

// MARK: - Claude

/// Restarting Claude Desktop, which is the only way it picks up an MCP server it was started
/// without.
///
/// Terminates rather than kills, and relaunches once the process has actually gone: `open` on a
/// still-running app just activates it, so a relaunch fired immediately would look like it worked
/// and leave the old process — and the old config — in place.
@MainActor
enum ClaudeRelaunch {
    static let bundleIdentifier = "com.anthropic.claudefordesktop"

    static var isInstalled: Bool {
        NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleIdentifier) != nil
    }

    static func perform() -> Bool {
        guard let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleIdentifier)
        else { return false }

        let running = NSRunningApplication.runningApplications(withBundleIdentifier: bundleIdentifier)
        guard !running.isEmpty else {
            launch(url)
            return true
        }
        for application in running { application.terminate() }

        Task {
            // Bounded: a Claude that refuses to quit is the user's decision to make, and the
            // tutorial says so rather than waiting forever.
            for _ in 0..<40 {
                if NSRunningApplication.runningApplications(withBundleIdentifier: bundleIdentifier)
                    .allSatisfy({ $0.isTerminated }) { break }
                try? await Task.sleep(for: .milliseconds(250))
            }
            launch(url)
        }
        return true
    }

    private static func launch(_ url: URL) {
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = true
        NSWorkspace.shared.openApplication(at: url, configuration: configuration)
    }
}
