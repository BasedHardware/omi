import AppKit

/// Watches the system clipboard for changes and emits the new string
/// content via a callback. Used by the ConnectSheet to auto-fill the
/// Telegram bot-token field when the user copies a token from
/// @BotFather and returns to the desktop.
///
/// Design notes
///
/// The watcher is split into TWO injectable sources: a cheap
/// change-count reader and an expensive string reader. The
/// change-count reader runs every tick; the string reader only
/// runs when the count has moved. P1 (cubic follow-up): the
/// previous single-source design read the string on every tick,
/// wasting CPU and triggering unnecessary pasteboard reads.
///
/// NSPasteboard.changeCount is O(1) and side-effect-free. Reading
/// the string content has measurable cost (NSPasteboard round-trips
/// through the pasteboard service and copies the data into the
/// caller's address space). For a 1s poll interval on a steady-state
/// clipboard (no changes), this matters — we burn zero CPU per
/// tick instead of one string-read per second.
///
/// Some password managers / clipboard managers spam changeCount to
/// obscure which apps are reading. We treat any string-content
/// change as a candidate for auto-fill; the watcher's job is just
/// "tell me when the string content changes", not "verify the
/// origin".
///
/// Thread safety
///
/// `NSPasteboard.general` must be read on the main thread. The
/// watcher dispatches its callback via `MainActor.run` so callers can
/// safely update SwiftUI @State directly from the callback.
@MainActor
final class ClipboardWatcher {

    /// Called whenever the clipboard string content changes. Receives
    /// the new string content.
    typealias ChangeHandler = (String) -> Void

    /// Cheap, side-effect-free read of the current clipboard change
    /// count. Default reads NSPasteboard.general.changeCount (O(1)
    /// integer, no data copy). Override in tests to inject a fake
    /// change count without touching the real pasteboard.
    typealias ChangeCountSource = () -> Int

    /// Reads the current clipboard string content. Expensive
    /// (NSPasteboard round-trip + data copy). Only called AFTER the
    /// change count has moved. Override in tests.
    typealias StringSource = () -> String?

    /// Default change-count source.
    static let systemChangeCountSource: ChangeCountSource = {
        NSPasteboard.general.changeCount
    }

    /// Default string source.
    static let systemStringSource: StringSource = {
        NSPasteboard.general.string(forType: .string)
    }

    private let changeCountSource: ChangeCountSource
    private let stringSource: StringSource
    private let pollInterval: TimeInterval
    private let handler: ChangeHandler
    private var timer: Timer?
    private var lastChangeCount: Int

    /// Start watching the clipboard.
    ///
    /// - Parameters:
    ///   - changeCountSource: Cheap O(1) read of the clipboard
    ///     change count. Default: NSPasteboard.general.changeCount.
    ///   - stringSource: Expensive read of the clipboard string
    ///     content. Only called after changeCountSource reports a
    ///     change. Default: NSPasteboard.general.string(forType:).
    ///   - pollInterval: Seconds between checks. Default 1.0s.
    ///   - handler: Called on the main actor whenever the clipboard
    ///     string content changes.
    init(
        changeCountSource: @escaping ChangeCountSource = ClipboardWatcher.systemChangeCountSource,
        stringSource: @escaping StringSource = ClipboardWatcher.systemStringSource,
        pollInterval: TimeInterval = 1.0,
        handler: @escaping ChangeHandler
    ) {
        self.changeCountSource = changeCountSource
        self.stringSource = stringSource
        self.pollInterval = pollInterval
        self.handler = handler
        // Seed with the current changeCount so the very first tick
        // doesn't fire if the clipboard hasn't changed since startup.
        self.lastChangeCount = changeCountSource()
    }

    /// Begin polling. Safe to call repeatedly — only the first call
    /// actually starts a timer.
    func start() {
        guard timer == nil else { return }
        let timer = Timer(timeInterval: pollInterval, repeats: true) { [weak self] _ in
            // Timer fires on the run loop the timer was scheduled on.
            // .common modes ensures it fires during modal interactions
            // (e.g. if a sheet is open and the run loop is in .modal).
            // The handler itself hops to MainActor.
            Task { @MainActor [weak self] in
                self?.checkClipboard()
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    /// Stop polling. Safe to call repeatedly. Also called from `deinit`.
    func stop() {
        timer?.invalidate()
        timer = nil
    }

    /// True if the polling timer is currently scheduled. Used by unit
    /// tests (P2 from cubic AI review, PR #8682) to assert that
    /// `stop()` actually invalidates the timer — checking this is more
    /// reliable than spinning a real Timer with a 10ms poll interval
    /// and racing against its dispatch-to-MainActor Task.
    var isRunning: Bool {
        timer != nil
    }

    deinit {
        timer?.invalidate()
    }

    /// Check whether the clipboard changed since the last tick. If yes,
    /// emit the new string content (if any). Public so unit tests can
    /// drive the check synchronously without spinning up a real timer.
    ///
    /// Two-step read: first the cheap change-count, then the string
    /// only if the count moved. P1 (cubic follow-up): pre-fix version
    /// read the string on every tick.
    func checkClipboard() {
        let currentCount = changeCountSource()
        guard currentCount != lastChangeCount else { return }
        lastChangeCount = currentCount

        // Now that we know the count changed, pay the cost of reading
        // the string content.
        guard let newContent = stringSource(), !newContent.isEmpty else {
            return
        }
        handler(newContent)
    }
}