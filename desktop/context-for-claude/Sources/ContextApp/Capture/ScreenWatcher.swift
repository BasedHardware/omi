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
@MainActor
final class ScreenWatcher {

    /// Called on the main actor for each frame worth storing. Ticks that change nothing call nothing.
    var onFrame: ((Frame) -> Void)?

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
        if let reason = ScreenPipeline.exclusionReason(appName: appName, bundleID: bundleID, title: nil) {
            noteSkip(reason)
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

        if let reason = ScreenPipeline.exclusionReason(
            appName: appName, bundleID: bundleID, title: windowTitle)
        {
            noteSkip(reason)
            return
        }

        guard let image = await capture(window) else { return }
        lastSkipReason = nil

        let capturedAt = ContextTime.now
        let hash = ScreenPipeline.dHash(of: image)
        let seenRecently = recentHashes.contains { ScreenPipeline.isSameScreen(hash, $0) }

        guard !seenRecently else {
            // Idle or oscillating screen: no OCR, no JPEG, and no row at all unless the user moved
            // to a different window — a duplicate row every 3 seconds would bury the timeline it is
            // meant to be.
            if appName != lastAppName || windowTitle != lastWindowTitle {
                emit(Frame(capturedAt: capturedAt, appName: appName, windowTitle: windowTitle))
            }
            return
        }
        remember(hash)

        // Whether this window is already the newest row on the timeline. Computed here because the
        // decision it feeds — is there enough new text to be worth a row — has to be made before
        // the JPEG is written, and `lastAppName`/`lastWindowTitle` belong to this actor.
        let repeatsLastStoredWindow = appName == lastAppName && windowTitle == lastWindowTitle

        let captured = CapturedImage(image: image)
        let processed = await Task.detached(priority: .utility) {
            ScreenPipeline.process(
                captured,
                capturedAt: capturedAt,
                repeatsLastStoredWindow: repeatsLastStoredWindow
            )
        }.value

        guard let processed else {
            // Pixels moved but no readable text arrived, in a window that is already the last row
            // stored — a spinner advancing, a progress bar filling, a repaint. The row would say
            // nothing the row before it does not already say, so it costs a row, a JPEG, and an FTS
            // entry for nothing.
            return
        }

        emit(
            Frame(
                capturedAt: capturedAt,
                appName: appName,
                windowTitle: windowTitle,
                ocrText: processed.ocrText,
                imagePath: processed.imagePath
            )
        )
    }

    /// Records a screen we have now seen, evicting the oldest once the ring is full.
    private func remember(_ hash: UInt64) {
        recentHashes.append(hash)
        if recentHashes.count > ScreenPipeline.recentScreenMemory {
            recentHashes.removeFirst()
        }
    }

    private func emit(_ frame: Frame) {
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
        guard let size = ScreenPipeline.captureSize(for: window.frame) else {
            noteSkip("window has no area")
            return nil
        }
        let config = SCStreamConfiguration()
        config.width = size.width
        config.height = size.height
        config.scalesToFit = true
        config.showsCursor = false

        do {
            return try await SCScreenshotManager.captureImage(
                contentFilter: SCContentFilter(desktopIndependentWindow: window),
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

    /// Longest side of both the OCR input and the stored JPEG.
    static let maxPixelSize = 1600
    static let jpegQuality: CGFloat = 0.5
    /// Titles can therefore lag reality by up to this long; the OCR text on the same row is always
    /// current, and the next tick corrects the title.
    static let shareableContentTTL: TimeInterval = 5
    /// Hamming distance below which two dHashes count as the same screen. Exact equality would be
    /// useless: a blinking caret or a ticking menu-bar clock flips a bit or two every tick and
    /// would force a full OCR pass on a screen nobody is touching. Empirically a spinner differs by
    /// 1 bit, a moved text cursor by ~4, and a real content change by 20+.
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

    // MARK: Exclusions

    /// Why this window must not be read, or nil if it may be. The reason is the skip-log line.
    ///
    /// Called twice per tick — once with no title, before the WindowServer is asked anything, and
    /// once with one. The same policy both times; the second call simply has more evidence.
    ///
    /// The credential half of it lives in `Redaction` so it can be unit-tested without a screen.
    /// `Redaction` is asked twice because `app` matches either identifier form and this is the one
    /// caller that holds both: the bundle id carries the title, and the display name catches the
    /// vendors whose bundle id says nothing (a rebranded password manager still calls itself one).
    /// The title is never put in the reason — a window excluded *because of* its title is exactly
    /// the one whose title should not be written down.
    static func exclusionReason(appName: String, bundleID: String, title: String?) -> String? {
        if isOwnOutput(appName: appName, bundleID: bundleID, title: title) {
            return "own output: \(appName)"
        }
        if Redaction.isSensitiveWindow(app: bundleID, title: nil)
            || Redaction.isSensitiveWindow(app: appName, title: nil)
        {
            return "excluded app: \(appName)"
        }
        if Redaction.isSensitiveWindow(app: bundleID, title: title)
            || Redaction.isSensitiveWindow(app: appName, title: title)
        {
            return "sensitive window in \(appName)"
        }
        return nil
    }

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

    /// Capture dimensions that preserve aspect ratio and stay within `maxPixelSize`.
    /// A zero-area window makes the ratio NaN, and `Int(NaN)` traps rather than throwing — so a
    /// degenerate frame is refused here instead of crashing the app.
    static func captureSize(for frame: CGRect) -> (width: Int, height: Int)? {
        guard frame.width > 0, frame.height > 0,
            frame.width.isFinite, frame.height.isFinite
        else { return nil }

        let scale = min(1, CGFloat(maxPixelSize) / max(frame.width, frame.height))
        return (
            max(1, Int((frame.width * scale).rounded())),
            max(1, Int((frame.height * scale).rounded()))
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

    // MARK: Off-main work

    /// Reads the frame and decides whether it earns a row. Nil means store nothing at all.
    static func process(
        _ captured: CapturedImage,
        capturedAt: Double,
        repeatsLastStoredWindow: Bool
    ) -> ProcessedFrame? {
        // Detached tasks run on the cooperative pool, which does not drain autorelease pools; the
        // CoreGraphics and Vision temporaries below would otherwise accumulate for the app's life.
        autoreleasepool { () -> ProcessedFrame? in
            let text = recognizeText(in: captured.image)

            // Judged before the JPEG is written rather than after: a frame nobody stores must leave
            // nothing behind, and an orphaned JPEG is never cleaned up — pruning walks the frames
            // table, so a file with no row outlives the database itself.
            if repeatsLastStoredWindow, contentLength(of: text) < minimumContentCharacters {
                return nil
            }

            let path = writeJPEG(captured.image, capturedAt: capturedAt)
            return ProcessedFrame(ocrText: text, imagePath: path)
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
    /// What this does *not* protect is the JPEG written beside the row: it still holds the pixels
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

    static func writeJPEG(_ image: CGImage, capturedAt: Double) -> String? {
        let sized = downscaled(image, longestSide: maxPixelSize) ?? image
        guard let data = jpegData(from: sized) else {
            ContextLog.error("Failed to encode frame JPEG", "screen")
            return nil
        }

        let directory = ContextPaths.framesDirectory(for: capturedAt)
        let name = "frame_\(fileStampFormatter.string(from: Date(timeIntervalSince1970: capturedAt))).jpg"
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let url = directory.appendingPathComponent(name)
            try data.write(to: url, options: .atomic)
            return url.path
        } catch {
            ContextLog.error("Failed to write frame JPEG: \(error.localizedDescription)", "screen")
            return nil
        }
    }

    static let fileStampFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HHmmss_SSS"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter
    }()

    /// Belt and braces: the capture is already requested at `maxPixelSize`, but the stored JPEG must
    /// honour the bound whatever ScreenCaptureKit hands back.
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

    static func jpegData(from image: CGImage) -> Data? {
        let data = NSMutableData()
        guard
            let destination = CGImageDestinationCreateWithData(
                data as CFMutableData,
                "public.jpeg" as CFString,
                1,
                nil
            )
        else { return nil }

        CGImageDestinationAddImage(
            destination,
            image,
            [kCGImageDestinationLossyCompressionQuality: jpegQuality] as CFDictionary
        )
        guard CGImageDestinationFinalize(destination) else { return nil }
        return data as Data
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
