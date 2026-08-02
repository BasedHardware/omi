import ContextCore
import AppKit
import CoreGraphics
import CoreImage
import Foundation
import ImageIO
import ScreenCaptureKit
import Vision

/// Samples the active window on a timer, reads it with Vision when the pixels actually changed, and
/// hands every worthwhile observation to `onFrame`.
///
/// Two costs shape this class, because it runs for the whole life of the machine: enumerating
/// windows through the WindowServer, and Vision OCR. The first is amortised behind a cached
/// `SCShareableContent` snapshot; the second is gated on a perceptual hash of the capture, so a
/// screen nobody is touching costs one small screenshot and nothing else.
///
/// Three rules decide what a tick is allowed to produce, and all three exist because a frame here is
/// permanent, searchable, and quoted back to a model:
///
/// - **Nothing sensitive is read.** `Redaction.isSensitiveWindow` refuses the window outright, and
///   `Redaction.scrub` runs on the title and on the OCR result before either can be handed on.
/// - **Nothing of ours is read.** This app's own window, Claude Desktop, and terminals running
///   Claude Code are skipped, so the assistant's output cannot be recycled into its own memory.
/// - **Nothing empty is stored.** Recent screens are remembered as a ring, and a frame with almost
///   no text in a window that is already the newest row is dropped rather than written.
///
/// Against those three sits one rule pushing the other way, because a gate with no ceiling starves:
/// **nothing is silently forgotten.** The hash gate answers "is this a screen we have seen", and for
/// a window nobody is touching the answer is yes for as long as the user keeps looking at it — so
/// reading one document for an hour produced no rows at all, and sitting still in front of a
/// document is what reading looks like. A capture suppressed for
/// ``ScreenPipeline/forceCaptureInterval`` is stored regardless of how similar it looks.
@MainActor
final class ScreenWatcher {

    /// Called on the main actor for each frame worth storing. Ticks that change nothing call nothing.
    var onFrame: ((Frame) -> Void)?

    /// The subtrees of a captured accessibility tree, handed over *before* the frame that references
    /// them. Separate from `onFrame` because they are deduplicated against every earlier frame: most
    /// ticks contribute a handful of new rows to a table that already holds the rest of the window.
    var onAXNodes: (([AXNodeRecord]) -> Void)?

    // MARK: - Lifecycle

    private var loop: Task<Void, Never>?

    var isRunning: Bool { loop != nil }

    func start(interval: TimeInterval = 3.0) {
        guard loop == nil else { return }
        let period = max(0.5, interval)

        if !Self.hasPermission() {
            ContextLog.info("Screen Recording not granted yet — watcher will idle until it is", "screen")
        }

        loop = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.tick()
                // Sleep *after* the work. A repeating Timer would queue ticks behind a slow OCR
                // pass and then fire them back-to-back; this loop simply runs a little later.
                try? await Task.sleep(nanoseconds: UInt64(period * 1_000_000_000))
            }
        }
        ContextLog.info("Screen watcher started (every \(period)s)", "screen")
    }

    func stop() {
        guard let loop else { return }
        loop.cancel()
        self.loop = nil
        // Resuming should always produce one full observation: whatever is on screen after a pause
        // is new information regardless of what was there before.
        recentHashes.removeAll()
        lastAppName = nil
        lastWindowTitle = nil
        lastFullPassAt = nil
        lastSkipReason = nil
        cachedContent = nil
        cachedContentAt = nil
        ContextLog.info("Screen watcher stopped", "screen")
    }

    // MARK: - Permission

    /// `nonisolated` so the permissions layer can ask from any context; both calls are thread-safe.
    nonisolated static func hasPermission() -> Bool {
        CGPreflightScreenCaptureAccess()
    }

    /// Raises the system prompt. Screen Recording only takes effect after a relaunch, so callers
    /// must tell the user that rather than waiting on a return value.
    nonisolated static func requestPermission() {
        _ = CGRequestScreenCaptureAccess()
    }

    // MARK: - State carried between ticks

    /// Perceptual hashes of the last few *distinct* screens — the whole idle-cost story.
    ///
    /// A ring rather than a single previous hash because the frames that actually repeat do not
    /// repeat consecutively: a terminal spinner alternates between two or three renderings, a
    /// progress bar oscillates, a caret blinks against a changing clock. Compared only against its
    /// immediate predecessor every one of those looks like new content forever, which is where the
    /// bulk of the near-empty rows in the database came from.
    private var recentHashes: [UInt64] = []
    /// What the last *emitted* frame said, so a title-only change is still recorded.
    private var lastAppName: String?
    private var lastWindowTitle: String?

    /// When the OCR pipeline last ran, forced or not — the clock behind
    /// ``ScreenPipeline/forceCaptureInterval``. Nil until the first pass of a run.
    ///
    /// Deliberately "last full pass" rather than "last row written". The only pass that writes
    /// nothing is one the low-signal drop refused, and that only happens when the window already
    /// owns the newest row, so nothing is lost by counting it — whereas measuring from the last
    /// *row* would let a text-free window re-run OCR on every single tick forever.
    private var lastFullPassAt: Double?

    private var cachedContent: SCShareableContent?
    private var cachedContentAt: Date?

    private var lastSkipReason: String?
    private var lastErrorLoggedAt: Date?

    // MARK: - One tick

    private func tick() async {
        guard Self.hasPermission() else {
            noteSkip("Screen Recording permission not granted")
            return
        }
        guard !ScreenPipeline.isScreenLocked() else {
            noteSkip("screen locked")
            return
        }
        guard let frontApp = NSWorkspace.shared.frontmostApplication else {
            noteSkip("no frontmost application")
            return
        }

        let bundleID = frontApp.bundleIdentifier ?? ""
        let appName = frontApp.localizedName ?? (bundleID.isEmpty ? "Unknown" : bundleID)

        // Mission Control, App Exposé, Launchpad and Dock menus all make the Dock frontmost, and
        // none of them is a surface the user is reading.
        guard bundleID != ScreenPipeline.dockBundleIdentifier else {
            noteSkip("Mission Control")
            return
        }
        // Asked before the window is resolved so an app that must never be read costs no
        // WindowServer enumeration, and asked again below once there is a title to judge.
        guard !ScreenPipeline.isOwnOutput(appName: appName, bundleID: bundleID, title: nil) else {
            noteSkip("own output: \(appName)")
            return
        }
        if let reason = ExclusionEngine.shared.exclusionReason(for: CaptureSubject(bundleID: bundleID, appName: appName)) {
            noteSkip(reason.logDescription)
            return
        }

        guard let window = await activeWindow(pid: frontApp.processIdentifier) else {
            noteSkip("frontmost app has no capturable window: \(appName)")
            return
        }

        // Titles are stored and indexed exactly like OCR text, and a terminal title carrying
        // `--token=…` or a callback URL is the same leak, so the same scrub runs before this value
        // is compared, emitted, or written.
        let windowTitle = Redaction.scrub(window.title ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .nilIfEmpty

        guard !ScreenPipeline.isOwnOutput(appName: appName, bundleID: bundleID, title: windowTitle) else {
            noteSkip("own output: \(appName)")
            return
        }
        let subject = CaptureSubject(bundleID: bundleID, appName: appName, windowTitle: windowTitle)
        let admission = ExclusionEngine.shared.admit(subject)
        guard let ticket = admission.ticket else {
            noteSkip(admission.reason?.logDescription ?? "excluded")
            return
        }

        guard let image = await capture(window) else { return }
        lastSkipReason = nil

        let capturedAt = ContextTime.now
        let hash = ScreenPipeline.dHash(of: image)
        let seenRecently = recentHashes.contains { ScreenPipeline.isSameScreen(hash, $0) }
        // The gate has no ceiling of its own: a screen that stays inside `dedupeDistance` of one
        // already in the ring is suppressed for as long as it stays there, which for a document
        // being read is forever. This is that ceiling.
        let forced = seenRecently
            && ScreenPipeline.isForceDue(lastFullPassAt: lastFullPassAt, now: capturedAt)

        if seenRecently && !forced {
            // Idle or oscillating screen: no OCR, no image, and no row at all unless the user moved
            // to a different window — a duplicate row every 3 seconds would bury the timeline it is
            // meant to be.
            if appName != lastAppName || windowTitle != lastWindowTitle {
                emit(
                    Frame(
                        capturedAt: capturedAt,
                        appName: appName,
                        bundleId: bundleID.nilIfEmpty,
                        windowTitle: windowTitle),
                    ticket: ticket,
                    axNodes: [])
            }
            return
        }
        // Only genuinely new screens enter the ring — it is a memory of *distinct* screens, and a
        // forced capture is by definition one already in it. Re-adding it would evict a real
        // oscillation phase and hand the idle OCR cost straight back.
        if !seenRecently { remember(hash) }
        // Stamped before the pipeline runs rather than after it decides: the attempt is what costs,
        // so the next force is due a full interval from here whatever this one concludes.
        lastFullPassAt = capturedAt

        // Whether this window is already the newest row on the timeline. Computed here because the
        // decision it feeds — is there enough new text to be worth a row — has to be made before
        // the image is written, and `lastAppName`/`lastWindowTitle` belong to this actor.
        let repeatsLastStoredWindow = appName == lastAppName && windowTitle == lastWindowTitle

        let pid = frontApp.processIdentifier
        let captured = CapturedImage(image: image)
        let processed = await Task.detached(priority: .utility) {
            ScreenPipeline.process(
                captured,
                capturedAt: capturedAt,
                repeatsLastStoredWindow: repeatsLastStoredWindow,
                pid: pid
            )
        }.value

        guard let processed else {
            // Pixels moved but no readable text arrived, in a window that is already the last row
            // stored — a spinner advancing, a progress bar filling, a repaint. The row would say
            // nothing the row before it does not already say, so it costs a row, an image, and an FTS
            // entry for nothing.
            return
        }

        emit(
            Frame(
                capturedAt: capturedAt,
                appName: appName,
                // Already read at the top of the tick for the exclusion checks and, until now,
                // thrown away. It is the only reliable key back to the app on disk — the timeline
                // draws its icon from it rather than guessing at `<appName>.app` in a list of
                // directories. Empty becomes nil so "not recorded" stays one value in the column.
                bundleId: bundleID.nilIfEmpty,
                windowTitle: windowTitle,
                ocrText: processed.ocrText,
                imagePath: processed.imagePath,
                axText: processed.axText,
                axRootHash: processed.axRootHash
            ),
            ticket: ticket,
            axNodes: processed.axNodes
        )
    }

    /// Records a screen we have now seen, evicting the oldest once the ring is full.
    private func remember(_ hash: UInt64) {
        recentHashes.append(hash)
        if recentHashes.count > ScreenPipeline.recentScreenMemory {
            recentHashes.removeFirst()
        }
    }

    private func emit(_ frame: Frame, ticket: CaptureTicket, axNodes: [AXNodeRecord]) {
        if let reason = ExclusionEngine.shared.revalidate(ticket) {
            ExclusionEngine.shared.discard(frame, reason: reason)
            noteSkip(reason.logDescription)
            return
        }
        // Nodes before the frame, always. The frame carries a root hash into a table those rows have
        // to be in already, and both writes land on the same serialised queue in the order they are
        // handed over — so a frame is never stored pointing at a subtree nobody wrote.
        if !axNodes.isEmpty { onAXNodes?(axNodes) }
        lastAppName = frame.appName
        lastWindowTitle = frame.windowTitle
        onFrame?(frame)
    }

    // MARK: - Window resolution

    /// `SCShareableContent.excludingDesktopWindows` walks every on-screen window through the
    /// WindowServer. At this cadence that contends with other capture apps (Zoom share, CleanShot,
    /// Loom) and shows up as UI stalls, so one snapshot is reused for `shareableContentTTL`.
    private func shareableContent(forceRefresh: Bool) async -> SCShareableContent? {
        if !forceRefresh,
            let cachedContent,
            let cachedContentAt,
            Date().timeIntervalSince(cachedContentAt) < ScreenPipeline.shareableContentTTL
        {
            return cachedContent
        }
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(
                false,
                onScreenWindowsOnly: true
            )
            cachedContent = content
            cachedContentAt = Date()
            return content
        } catch {
            noteError("Shareable content unavailable: \(error.localizedDescription)")
            return nil
        }
    }

    private func activeWindow(pid: pid_t) async -> SCWindow? {
        if let content = await shareableContent(forceRefresh: false),
            let window = ScreenPipeline.frontWindow(in: content, pid: pid)
        {
            return window
        }
        // The app opened its window inside the cache window. One forced refresh is cheaper than
        // losing the first few seconds of everything the user newly opens.
        guard let fresh = await shareableContent(forceRefresh: true) else { return nil }
        return ScreenPipeline.frontWindow(in: fresh, pid: pid)
    }

    private func capture(_ window: SCWindow) async -> CGImage? {
        // The filter, not `window.frame`, is the authority on what will actually be captured and at
        // what backing scale — the frame knows neither. Both properties are macOS 14.0+ and the
        // deployment floor here is 14.4.
        let filter = SCContentFilter(desktopIndependentWindow: window)
        guard
            let size = ScreenPipeline.captureSize(
                for: filter.contentRect,
                pointPixelScale: CGFloat(filter.pointPixelScale)
            )
        else {
            noteSkip("window has no area")
            return nil
        }

        let config = SCStreamConfiguration()
        config.width = size.width
        config.height = size.height
        config.scalesToFit = true
        config.showsCursor = false
        // Asking for more pixels than the nominal size is pointless if the source is downsampled
        // first, so take the native backing store.
        config.captureResolution = .best

        do {
            return try await SCScreenshotManager.captureImage(
                contentFilter: filter,
                configuration: config
            )
        } catch {
            noteError("Capture failed: \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - Logging that cannot spam

    /// A skip repeats every tick for as long as the condition holds; log only the transition.
    private func noteSkip(_ reason: String) {
        guard lastSkipReason != reason else { return }
        lastSkipReason = reason
        ContextLog.info("Skipping capture: \(reason)", "screen")
    }

    private func noteError(_ message: String) {
        let now = Date()
        if let lastErrorLoggedAt, now.timeIntervalSince(lastErrorLoggedAt) < 60 { return }
        lastErrorLoggedAt = now
        ContextLog.error(message, "screen")
    }
}

// MARK: - Off-actor pipeline

/// A `CGImage` handed to a background task. CoreGraphics images are immutable once created, so
/// crossing an isolation boundary with one is safe; the compiler just cannot prove it.
private struct CapturedImage: @unchecked Sendable {
    let image: CGImage
}

private struct ProcessedFrame: Sendable {
    let ocrText: String?
    let imagePath: String?
    let axText: String?
    let axRootHash: Data?
    let axNodes: [AXNodeRecord]
}

/// Vision writes its observations from inside `perform`, synchronously, before it returns — so this
/// box is never touched from two threads even though the block signature allows it.
private final class TextSink: @unchecked Sendable {
    var lines: [String] = []
    var failure: Error?
}

/// Everything that must run off the main actor, plus the pure policy that decides what is worth
/// capturing at all. Declared at file scope so none of it inherits `ScreenWatcher`'s isolation.
private enum ScreenPipeline {

    // MARK: Tunables

    /// Longest side of the stored frame image. Storage only — it must never decide what Vision sees.
    static let maxPixelSize = 1600

    /// Longest side of the image handed to Vision.
    ///
    /// Split from ``maxPixelSize`` because one constant governing both meant OCR resolution could
    /// not be tuned without changing storage, and the storage bound won.
    ///
    /// Measured, not chosen: `.accurate` recognition of a screenful of UI text is non-monotonic in
    /// input size and peaks near 2400 px on the longest side. On this machine's built-in display,
    /// identifier recall was 88% at the 1512 px that shipped, 96% at 2400 px, and **75% at the
    /// native 3024 px** — so "just OCR the native image" is worse than the defect it would be
    /// fixing, and both sides of the band are bad. Latency is flat across the whole range
    /// (0.67–0.96 s) because Vision's cost tracks the number of text regions rather than the pixel
    /// count, so this is an accuracy decision and not a battery one. It is an empirical optimum
    /// from one fixture family on one machine: re-run the sweep in `docs/ocr-quality.md` §3 before
    /// moving it, and re-run it whenever the pinned Vision revision changes.
    static let ocrMaxPixelSize = 2400

    /// Quality of the stored frame image, which is HEIC rather than JPEG.
    ///
    /// The number is low because the retention policy makes it the honest choice, and it was picked
    /// by measurement, not taste. Encoding 60 real frames from this machine through the exact path
    /// below — same downscale, same `CGImageDestination` call — gave, per frame:
    ///
    ///     jpeg q0.50   183.1 KB     heic q0.30    90.3 KB  (-51%)
    ///     heic q0.50   131.1 KB     heic q0.25    80.3 KB  (-56%)
    ///     heic q0.40   110.2 KB     heic q0.20    68.4 KB  (-63%)
    ///
    /// Note HEIC's quality scale is not JPEG's: 0.5 buys only 28%, and matching a "low" preset from
    /// `sips` takes roughly 0.15. Anyone re-tuning this must re-measure rather than reason from the
    /// JPEG number they replaced.
    ///
    /// Why it matters: capture burns ~200 MB a day, `defaultRetentionDays` is 30, and
    /// `defaultFrameBytesCap` is 4 GB. As JPEG that is ~6 GB for the window the policy promises, so
    /// the byte cap bit around three weeks in and silently deleted the rest — the user lost history
    /// the settings told them they had. At this quality the same 30 days is ~2.2 GB, under the cap
    /// with room for a heavier week, and the promise holds.
    ///
    /// Fidelity is the cheap side of that trade because nothing decodes these files: no MCP tool
    /// returns pixels and the uploader sends only text. OCR reads a separate, larger image
    /// (``ocrMaxPixelSize``) before this one is written and is untouched by this number. Keeping a
    /// month at lower fidelity beats keeping three weeks at higher fidelity and calling it a month.
    static let frameQuality: CGFloat = 0.20

    /// Longest accessibility text stored per frame.
    ///
    /// Generous next to a window title and mean next to a document: the point is the labels, values
    /// and controls a person was actually looking at, not the whole scrollback of a text view. The
    /// walker's own per-node and total-text ceilings do most of this work already; this is the last
    /// bound before the column.
    static let maxAXTextCharacters = 8_000
    /// Titles can therefore lag reality by up to this long; the OCR text on the same row is always
    /// current, and the next tick corrects the title.
    static let shareableContentTTL: TimeInterval = 5
    /// Hamming distance below which two dHashes count as the same screen. Exact equality would be
    /// useless: a blinking caret or a ticking menu-bar clock flips a bit or two every tick and
    /// would force a full OCR pass on a screen nobody is touching. Empirically a spinner differs by
    /// 1 bit, a moved text cursor by ~4, and a real content change by 20+.
    ///
    /// That calibration was taken at the old capture size. `dHash` still renders to a fixed 9x8
    /// grid, but each cell now averages ~2.5x more source pixels, which should if anything make the
    /// hash steadier rather than noisier. `docs/ocr-quality.md` §4.3 asks for the two populations to
    /// be re-confirmed against logged hamming distances; ``forceCaptureInterval`` is what keeps a
    /// mis-calibration from being silent in the meantime, since no window can be suppressed forever.
    static let dedupeDistance = 5

    /// How many distinct recent screens a new capture is compared against.
    ///
    /// Eight covers the loops that actually occur — a two- or three-frame spinner, a window flipping
    /// between two states, an alt-tab back and forth — without being large enough to swallow real
    /// re-reading: at 3 s a tick, a screen has to be genuinely identical (within
    /// ``dedupeDistance``) to something inside the last handful of *different* screens to be
    /// skipped, and coming back to an unchanged window is not new information anyway. Only novel
    /// hashes enter the ring, so a spinner cannot flush the real screens out of it.
    static let recentScreenMemory = 8

    /// The longest a window may stay on screen without earning a row, however unchanged it looks.
    ///
    /// The ring answers "have we seen this screen" and nothing else, so it has no ceiling: a screen
    /// that never leaves the ``dedupeDistance`` ball around one of its entries is suppressed
    /// forever. That silently deleted the activity most worth remembering — measured against a
    /// rival recorder over the same two hours, Finder was missed *entirely* (1.8% of their capture,
    /// 0.0% of ours), Messages 11.7% vs 5.2%, Claude 10.7% vs 6.8%. Apps that sit still got
    /// suppressed, and sitting still in front of a document is what reading looks like.
    ///
    /// Sixty seconds, chosen against the consumer rather than picked round: `Queries.activity`
    /// closes an activity block when consecutive frames are more than 120 s apart. Forcing at half
    /// that keeps a continuously-viewed static window inside one unbroken block even when a tick is
    /// lost to a slow OCR pass or a missed window lookup, so "read one document for an hour" reads
    /// back as an hour rather than as absence. It also bounds the cost exactly: at most one extra
    /// OCR pass and one stored image per minute, a twentieth of what the 3 s tick could produce, and only
    /// while a window is otherwise being suppressed.
    static let forceCaptureInterval: Double = 60

    /// Letters and digits below which a frame is not worth a row of its own.
    ///
    /// Counted over content characters only, so spinner glyphs (`⠐`, `⠂`), box drawing, progress
    /// bars and window chrome score zero — which is what a tenth of the frames in the dogfooding
    /// database were. Twenty-five is roughly four short words: below any real sentence, above every
    /// decoration. It only ever applies when the window is *also* unchanged from the last stored
    /// frame, so the first sighting of a text-free window still gets recorded.
    static let minimumContentCharacters = 25

    static let dockBundleIdentifier = "com.apple.dock"

    /// Held for the process lifetime rather than built per request: a Swift array literal assigned
    /// to `recognitionLanguages` has call-frame lifetime, and Vision keeps enumerating the bridged
    /// NSArray on its own queue after the frame is gone (omi #5891, #5151 — a trap, not an error).
    static let recognitionLanguages: [String] = ["en-US"]

    // MARK: Not reading ourselves

    /// Claude Desktop. Anything else Anthropic ships is caught by the prefix below, because every
    /// bundle they ship is a surface where this assistant's own words are on screen.
    static let claudeDesktopBundleIdentifier = "com.anthropic.claudefordesktop"
    static let anthropicBundlePrefix = "com.anthropic."

    /// Terminal emulators, where Claude Code runs. The set exists only to gate the title check
    /// below: a terminal is otherwise ordinary and worth capturing.
    static let terminalBundleIdentifiers: Set<String> = [
        "com.apple.terminal",
        "com.googlecode.iterm2",
        "net.kovidgoyal.kitty",
        "com.mitchellh.ghostty",
        "io.alacritty",
        "org.alacritty",
        "com.github.wez.wezterm",
        "dev.warp.warp-stable",
        "dev.warp.warp-preview",
        "co.zeit.hyper",
        "org.tabby",
    ]

    /// Emulators ship under new bundle ids faster than a list can track; their names are stabler.
    static let terminalNameFragments = [
        "terminal", "iterm", "kitty", "ghostty", "alacritty", "wezterm", "warp", "hyper", "tabby",
    ]

    /// What marks a terminal window as one this assistant is running inside.
    ///
    /// There is no honest signal for "Claude Code is the process in this window" from outside it:
    /// the frontmost application is the emulator, not the CLI, and walking the process tree is a
    /// different permission and a different class of bug. The title is the cheap evidence available,
    /// and Claude Code writes its state into it — `✳` while it is working, and the word `claude` in
    /// the command-derived title most emulators set.
    ///
    /// **It catches:** a Terminal / iTerm2 / kitty / Ghostty / WezTerm / Alacritty / Warp / Hyper /
    /// Tabby window whose title mentions Claude or carries the `✳` marker. That is the shape of the
    /// 22-in-906 self-captures found in the database.
    ///
    /// **It does not catch:** Claude Code in an editor's integrated terminal (VS Code, Cursor,
    /// JetBrains) or inside a tmux/screen session that rewrites the title; an emulator configured to
    /// show only the working directory or the hostname; a background pane; or claude.ai in a browser
    /// tab. Nor does it distinguish "Claude Code is running here" from "this window happens to be in
    /// ~/claude-experiments" — a directory named after Claude loses its frames, which is the cheap
    /// side of the trade. The remaining hole is real, and the fix for it is a signal from the CLI
    /// rather than a longer list of guesses about titles.
    static let claudeCodeTitleMarkers = ["claude", "✳"]

    /// Windows whose text originates from this app or from Claude itself.
    ///
    /// Storing them is not a privacy problem, it is a correctness one: OCRing the assistant's own
    /// output back into the database means the next `recall` returns Claude's words as "context
    /// about the user's life", and every turn compounds the last one.
    static func isOwnOutput(appName: String, bundleID: String, title: String?) -> Bool {
        let bundle = bundleID.lowercased()
        let name = appName.lowercased()

        // `Bundle.main.bundleIdentifier` is nil under `swift run` and in tests, so the shipped id is
        // also compared literally — a dev build must not read itself either.
        if bundle == ContextPaths.bundleIdentifier { return true }
        if let own = Bundle.main.bundleIdentifier, bundleID == own { return true }

        if bundle == claudeDesktopBundleIdentifier || bundle.hasPrefix(anthropicBundlePrefix) {
            return true
        }
        // Claude Desktop as macOS reports its display name.
        if name == "claude" { return true }

        guard terminalBundleIdentifiers.contains(bundle)
            || terminalNameFragments.contains(where: { name.contains($0) })
        else { return false }

        guard let title = title?.lowercased() else { return false }
        return claudeCodeTitleMarkers.contains { title.contains($0) }
    }

    static func isScreenLocked() -> Bool {
        guard let session = CGSessionCopyCurrentDictionary() as? [String: Any] else { return false }
        if let locked = session["CGSSessionScreenIsLocked"] as? Bool, locked { return true }
        // Fast user switching: another account owns the console, so there is nothing of ours to read.
        if let onConsole = session["kCGSSessionOnConsoleKey"] as? Bool, !onConsole { return true }
        return false
    }

    // MARK: Window choice

    static func frontWindow(in content: SCShareableContent, pid: pid_t) -> SCWindow? {
        let candidates = content.windows.filter { window in
            window.owningApplication?.processID == pid
                && window.windowLayer == 0
                && window.frame.width > 100
                && window.frame.height > 100
        }
        guard let largest = candidates.map({ $0.frame.width * $0.frame.height }).max() else {
            return nil
        }
        // `windows` comes back front-to-back, so among equally large windows the first one is the
        // one the user is looking at rather than the backmost (omi #6552).
        return candidates.first { $0.frame.width * $0.frame.height == largest }
    }

    /// Pixel dimensions to capture, preserving aspect ratio.
    ///
    /// `SCContentFilter.contentRect` is in **points** while `SCStreamConfiguration.width`/`.height`
    /// are in **pixels** ("output width as measured in pixels"), so passing the point size straight
    /// through captured a Retina window at 1x and halved every glyph before Vision ever saw it. The
    /// old `min(1, …)` clamp made it worse, because it could only ever shrink: a 1920 pt window
    /// went out at 1600 px — 0.83x of the points, 0.42x of the pixels actually on screen — and
    /// measured 19.6% CER with 32% identifier recall, two thirds of the searchable terms destroyed.
    ///
    /// So: scale *up* towards the backing store, cap at ``ocrMaxPixelSize``, and never go below 1x.
    /// Below 1x throws away text that was on the screen; above the cap accuracy falls again (see
    /// ``ocrMaxPixelSize``). The stored image is brought back down separately in ``writeFrameImage``.
    ///
    /// A zero-area window makes the ratio NaN, and `Int(NaN)` traps rather than throwing — so a
    /// degenerate frame is refused here instead of crashing the app.
    static func captureSize(for rect: CGRect, pointPixelScale: CGFloat) -> (width: Int, height: Int)? {
        guard rect.width > 0, rect.height > 0,
            rect.width.isFinite, rect.height.isFinite
        else { return nil }

        // A missing, non-finite or sub-1 scale would shrink the capture below the point size, which
        // is the bug being fixed — fall back to 1x rather than trusting it.
        let backing = (pointPixelScale.isFinite && pointPixelScale >= 1) ? pointPixelScale : 1
        let longestPoints = max(rect.width, rect.height)
        let target = min(longestPoints * backing, CGFloat(ocrMaxPixelSize))
        let factor = max(1, target / longestPoints)
        return (
            max(1, Int((rect.width * factor).rounded())),
            max(1, Int((rect.height * factor).rounded()))
        )
    }

    // MARK: Dedupe

    /// Perceptual difference hash: 9x8 grayscale, each pixel compared to its right neighbour.
    /// Localised motion (a cursor, a spinner) moves one or two bits; new content moves many.
    static func dHash(of image: CGImage) -> UInt64 {
        let width = 9
        let height = 8
        guard
            let context = CGContext(
                data: nil,
                width: width,
                height: height,
                bitsPerComponent: 8,
                bytesPerRow: width,
                space: CGColorSpaceCreateDeviceGray(),
                bitmapInfo: CGImageAlphaInfo.none.rawValue
            )
        else { return 0 }

        context.interpolationQuality = .low
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))

        guard let data = context.data else { return 0 }
        let pixels = data.assumingMemoryBound(to: UInt8.self)

        var hash: UInt64 = 0
        for row in 0..<height {
            for column in 0..<(width - 1) {
                let index = row * width + column
                if pixels[index] > pixels[index + 1] {
                    hash |= 1 << (row * (width - 1) + column)
                }
            }
        }
        return hash
    }

    static func isSameScreen(_ lhs: UInt64, _ rhs: UInt64) -> Bool {
        (lhs ^ rhs).nonzeroBitCount <= dedupeDistance
    }

    /// Whether the dedup gate has suppressed everything for long enough that the next frame must be
    /// stored regardless of how similar it looks. See ``forceCaptureInterval``.
    ///
    /// No prior pass means due: the first capture of a run is always worth storing.
    static func isForceDue(lastFullPassAt: Double?, now: Double) -> Bool {
        guard let lastFullPassAt else { return true }
        let elapsed = now - lastFullPassAt
        // Wall-clock, so an NTP correction or a wake from sleep can put `now` behind the last pass.
        // A backwards jump counts as due rather than wedging capture until real time catches up.
        return elapsed < 0 || elapsed >= forceCaptureInterval
    }

    // MARK: Off-main work

    /// Reads the frame and decides whether it earns a row. Nil means store nothing at all.
    static func process(
        _ captured: CapturedImage,
        capturedAt: Double,
        repeatsLastStoredWindow: Bool,
        pid: pid_t
    ) -> ProcessedFrame? {
        // Detached tasks run on the cooperative pool, which does not drain autorelease pools; the
        // CoreGraphics and Vision temporaries below would otherwise accumulate for the app's life.
        autoreleasepool { () -> ProcessedFrame? in
            let text = recognizeText(in: captured.image)

            // Judged before the image is written rather than after: a frame nobody stores must leave
            // nothing behind, and an orphaned image is never cleaned up — pruning walks the frames
            // table, so a file with no row outlives the database itself.
            if repeatsLastStoredWindow, contentLength(of: text) < minimumContentCharacters {
                return nil
            }

            let path = writeFrameImage(captured.image, capturedAt: capturedAt)

            // The same window, read rather than looked at. Done here, off the main actor, because
            // every attribute is a synchronous message to another process: an application that is
            // beachballing would otherwise stall the tick that is trying to observe it. The walker's
            // own wall-clock budget is what bounds that, and a window that answers nothing simply
            // leaves these nil — OCR above has already produced a usable row either way.
            var axText: String?
            var axRootHash: Data?
            var axNodes: [AXNodeRecord] = []
            if Permissions.check(.accessibility),
               let window = AXElement.focusedWindow(pid: pid),
               let tree = AccessibilityTree.capture(window) {
                axText = AccessibilityTree
                    .flattenedText(of: tree, limit: maxAXTextCharacters)
                    .nilIfEmpty
                axRootHash = AccessibilityTree.rootHash(of: tree)
                axNodes = AccessibilityTree.records(of: tree)
            }

            return ProcessedFrame(
                ocrText: text,
                imagePath: path,
                axText: axText,
                axRootHash: axRootHash,
                axNodes: axNodes)
        }
    }

    /// Letters and digits in `text`, ignoring whitespace, punctuation and symbols.
    ///
    /// Symbols are what a low-signal frame is made of — a Braille spinner, a block-drawing progress
    /// bar, a row of window-chrome glyphs — and counting them would let exactly the frames this is
    /// meant to catch pass as content.
    static func contentLength(of text: String?) -> Int {
        guard let text else { return 0 }
        var count = 0
        for scalar in text.unicodeScalars where contentCharacters.contains(scalar) { count += 1 }
        return count
    }

    static let contentCharacters = CharacterSet.letters.union(.decimalDigits)

    /// OCR, scrubbed. The raw recognition result never leaves this function.
    ///
    /// This is the only place OCR text is produced, which is what makes "redact before the write"
    /// enforceable rather than a habit: there is no path from Vision to the database that could skip
    /// the scrub. Redacting afterwards would be theatre — the plaintext would already be in the
    /// file, in the WAL, and in any backup taken between the two.
    ///
    /// What this does *not* protect is the image written beside the row: it still holds the pixels
    /// the credential was drawn in. Images are not searched and not returned by any MCP tool, so a
    /// secret cannot be recalled out of one, but anyone with the frames directory can look. Fixing
    /// that means not writing the image when a scrub fires, which is a bigger behaviour change than
    /// this one and belongs with the retention policy.
    static func recognizeText(in image: CGImage) -> String? {
        let sink = TextSink()
        let request = VNRecognizeTextRequest { request, error in
            if let error {
                sink.failure = error
                return
            }
            guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
            // Defensive copy: Vision returns a bridged NSArray whose buffer can be released
            // underneath an enumeration, which traps the process instead of throwing (#5891, #5151).
            sink.lines = Array(observations).compactMap { $0.topCandidates(1).first?.string }
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.recognitionLanguages = recognitionLanguages

        // Pinned rather than left on whatever `currentRevision` the running OS ships. `frames_fts`
        // is durable and never re-OCR'd, so an OS update that changed the recogniser would split
        // the index down the middle: text stored last month stops matching text stored tomorrow,
        // unreproducibly, and nothing in the product could explain why. Revision 3 is the newest
        // this SDK defines and 1 and 2 are deprecated as of macOS 15, so this is a behavioural
        // no-op today — its entire job is to make a future revision 4 a decision with a
        // re-measurement attached rather than a silent corpus change.
        request.revision = VNRecognizeTextRequestRevision3

        // Explicitly the most permissive setting, and pinned for the same reason as the revision.
        //
        // Worth stating because the obvious value is wrong here: 1/32 (0.03125) is the default for
        // `VNDetectTextRectanglesRequest`, *not* for this request, whose documented and
        // probe-confirmed default is 0.0. The SDK is unambiguous — "if the minimum height is set to
        // 0.0 the image gets processed at the highest possible resolution with no downscaling …
        // the smallest technically readable text will be recognized". So there is no recall to buy
        // by lowering this: any non-zero value, 0.015 included, is a *raise* that makes Vision
        // downscale and loses exactly the dense IDE and terminal text such a change is meant to
        // win. The only lever on glyph height is the image handed in, which is `captureSize`.
        request.minimumTextHeight = 0

        do {
            try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
        } catch {
            ContextLog.error("OCR failed: \(error.localizedDescription)", "screen")
            return nil
        }
        if let failure = sink.failure {
            ContextLog.error("OCR failed: \(failure.localizedDescription)", "screen")
            return nil
        }
        return Redaction.scrub(sink.lines.joined(separator: "\n"))
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .nilIfEmpty
    }

    static func writeFrameImage(_ image: CGImage, capturedAt: Double) -> String? {
        let sized = downscaled(image, longestSide: maxPixelSize) ?? image
        guard let data = frameImageData(from: sized) else {
            ContextLog.error("Failed to encode frame image", "screen")
            return nil
        }

        // The extension changes with the format, and nothing downstream cares: `frames.imagePath`
        // is opaque text, and both prune paths delete by path rather than by suffix. So the older
        // `.jpg` files already on disk keep working and expire on the same schedule — the format
        // change needs no migration and no dual-read path.
        let directory = ContextPaths.framesDirectory(for: capturedAt)
        let name = "frame_\(fileStampFormatter.string(from: Date(timeIntervalSince1970: capturedAt))).heic"
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            ContextPaths.setPermissions(directory, mode: 0o700)
            let url = directory.appendingPathComponent(name)
            try data.write(to: url, options: .atomic)
            ContextPaths.setPermissions(url, mode: 0o600)
            return url.path
        } catch {
            ContextLog.error("Failed to write frame image: \(error.localizedDescription)", "screen")
            return nil
        }
    }

    static let fileStampFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HHmmss_SSS"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter
    }()

    /// Brings the stored frame image back to `maxPixelSize`.
    ///
    /// This used to be a no-op, because the capture itself was clamped to 1600 — which is precisely
    /// why the OCR input size could not be raised without inflating storage. Now the capture is
    /// sized for Vision (up to `ocrMaxPixelSize`) and this is the only thing holding the stored
    /// image where it has always been.
    static func downscaled(_ image: CGImage, longestSide: Int) -> CGImage? {
        let longest = max(image.width, image.height)
        guard longest > longestSide else { return nil }

        let scale = CGFloat(longestSide) / CGFloat(longest)
        let width = max(1, Int((CGFloat(image.width) * scale).rounded()))
        let height = max(1, Int((CGFloat(image.height) * scale).rounded()))
        guard
            let context = CGContext(
                data: nil,
                width: width,
                height: height,
                bitsPerComponent: 8,
                bytesPerRow: 0,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
            )
        else { return nil }

        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        return context.makeImage()
    }

    static func frameImageData(from image: CGImage) -> Data? {
        let data = NSMutableData()
        guard
            let destination = CGImageDestinationCreateWithData(
                data as CFMutableData,
                "public.heic" as CFString,
                1,
                nil
            )
        else { return nil }

        CGImageDestinationAddImage(
            destination,
            image,
            [kCGImageDestinationLossyCompressionQuality: frameQuality] as CFDictionary
        )
        guard CGImageDestinationFinalize(destination) else { return nil }
        return data as Data
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
