import AppKit

/// Watches the system clipboard for changes and emits the new string
/// content via a callback. Used by the ConnectSheet to auto-fill the
/// Telegram bot-token field when the user copies a token from
/// @BotFather and returns to the desktop.
///
/// Design notes
///
/// We use NSPasteboard.changeCount() (incremented by AppKit on every
/// clipboard mutation) rather than polling the contents every tick.
/// changeCount is O(1) and side-effect-free, so we can poll it cheaply
/// (every 1s) without copying the clipboard data on every tick —
/// only when it changes. Some password managers / clipboard managers
/// spam changeCount to obscure which apps are reading; we treat any
/// string-content change as a candidate for auto-fill.
///
/// Testability
///
/// The pasteboard source is injected as a closure rather than the
/// NSPasteboard instance directly. Reason: xctest runs in a sandbox
/// that doesn't have access to the system pasteboard — changeCount
/// is pinned at startup and never bumps, so the production code
/// path is untestable as-is. The injected closure can be a fake in
/// tests (increment-on-write) or the real NSPasteboard.general in
/// production.
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

    /// Snapshot of clipboard state at one moment in time.
    struct Snapshot {
        let changeCount: Int
        let string: String?
    }

    /// Reads the current clipboard state. Default uses NSPasteboard.general.
    /// Override in tests to use a fake pasteboard.
    typealias Source = () -> Snapshot

    private let source: Source
    private let pollInterval: TimeInterval
    private let handler: ChangeHandler
    private var timer: Timer?
    private var lastChangeCount: Int

    /// Default source — reads NSPasteboard.general on the main thread.
    /// NSPasteboard reads are main-thread only, so this is a
    /// synchronous read (the caller's tick already happens on main).
    static let systemPasteboardSource: Source = {
        let pb = NSPasteboard.general
        return Snapshot(changeCount: pb.changeCount, string: pb.string(forType: .string))
    }

    /// Start watching the clipboard.
    ///
    /// - Parameters:
    ///   - source: A closure that returns the current clipboard snapshot.
    ///     Default: reads NSPasteboard.general. Override in tests.
    ///   - pollInterval: Seconds between checks. Default 1.0s.
    ///   - handler: Called on the main actor whenever the clipboard
    ///     string content changes.
    init(
        source: @escaping Source = ClipboardWatcher.systemPasteboardSource,
        pollInterval: TimeInterval = 1.0,
        handler: @escaping ChangeHandler
    ) {
        self.source = source
        self.pollInterval = pollInterval
        self.handler = handler
        // Seed with the current changeCount so the very first tick
        // doesn't fire if the clipboard hasn't changed since startup.
        self.lastChangeCount = source().changeCount
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

    deinit {
        timer?.invalidate()
    }

    /// Check whether the clipboard changed since the last tick. If yes,
    /// emit the new string content (if any). Public so unit tests can
    /// drive the check synchronously without spinning up a real timer.
    func checkClipboard() {
        let snapshot = source()
        guard snapshot.changeCount != lastChangeCount else { return }
        lastChangeCount = snapshot.changeCount

        // changeCount going up doesn't mean it's a string — the user
        // might have copied an image or file URL. Only emit if we got
        // actual string content.
        guard let newContent = snapshot.string, !newContent.isEmpty else {
            return
        }
        handler(newContent)
    }
}