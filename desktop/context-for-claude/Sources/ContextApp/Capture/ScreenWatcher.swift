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
        lastHash = nil
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

    /// Perceptual hash of the previous capture — the whole idle-cost story.
    private var lastHash: UInt64?
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
        guard !ScreenPipeline.isExcluded(appName: appName, bundleID: bundleID) else {
            noteSkip("excluded app: \(appName)")
            return
        }

        guard let window = await activeWindow(pid: frontApp.processIdentifier) else {
            noteSkip("frontmost app has no capturable window: \(appName)")
            return
        }

        let windowTitle = window.title?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        guard !ScreenPipeline.isSensitiveSettingsWindow(bundleID: bundleID, title: windowTitle) else {
            noteSkip("System Settings privacy pane")
            return
        }

        guard let image = await capture(window) else { return }
        lastSkipReason = nil

        let capturedAt = ContextTime.now
        let hash = ScreenPipeline.dHash(of: image)
        let unchanged = lastHash.map { ScreenPipeline.isSameScreen(hash, $0) } ?? false
        lastHash = hash

        guard !unchanged else {
            // Idle screen: no OCR, no JPEG, and no row at all unless the user moved to a different
            // window — a duplicate row every 3 seconds would bury the timeline it is meant to be.
            if appName != lastAppName || windowTitle != lastWindowTitle {
                emit(Frame(capturedAt: capturedAt, appName: appName, windowTitle: windowTitle))
            }
            return
        }

        let captured = CapturedImage(image: image)
        let processed = await Task.detached(priority: .utility) {
            ScreenPipeline.process(captured, capturedAt: capturedAt)
        }.value

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

    static let dockBundleIdentifier = "com.apple.dock"

    /// Held for the process lifetime rather than built per request: a Swift array literal assigned
    /// to `recognitionLanguages` has call-frame lifetime, and Vision keeps enumerating the bridged
    /// NSArray on its own queue after the frame is gone (omi #5891, #5151 — a trap, not an error).
    static let recognitionLanguages: [String] = ["en-US"]

    // MARK: Exclusions

    /// Surfaces that must never be read. Password managers are the reason this list exists at all —
    /// OCRing an unlocked vault would put real secrets in a plain-text database. The screenshot and
    /// screen-share tools are here because their windows are either our own capture UI reflected
    /// back or a picker showing someone else's screen.
    static let excludedBundleIdentifiers: Set<String> = [
        // Password managers and secret stores.
        "com.1password.1password",
        "com.1password.browser-support",
        "com.agilebits.onepassword7",
        "com.agilebits.onepassword-osx",
        "com.bitwarden.desktop",
        "com.dashlane.Dashlane",
        "com.lastpass.LastPass",
        "com.lastpass.lastpassmacdesktop",
        "org.keepassxc.keepassxc",
        "in.sinew.Enpass-Desktop",
        "com.nordpass.macos",
        "me.proton.pass.electron",
        "com.apple.keychainaccess",
        "com.apple.Passwords",
        // Authentication surfaces the system puts in front of the user.
        "com.apple.SecurityAgent",
        "com.apple.loginwindow",
        // Screenshot / screen-share tooling.
        "com.apple.screencaptureui",
        "com.apple.ScreenSharing",
        "com.apple.screensharing.agent",
        "com.apple.screensharing.MessagesAgent",
        "pl.maketheweb.cleanshotx",
        "com.loom.desktop",
        "cc.ffitch.shottr",
        "com.monosnap.monosnap",
        "com.skitch.skitch",
    ]

    /// Bundle IDs drift between versions and rebrands; these product names do not.
    static let excludedNameFragments = [
        "password", "keychain", "keepass", "bitwarden", "dashlane", "lastpass", "nordpass",
        "enpass", "authenticator", "screenshot", "screen sharing", "snagit",
    ]

    static let settingsBundleIdentifiers: Set<String> = [
        "com.apple.systempreferences", "com.apple.SystemPreferences",
    ]

    /// System Settings is ordinary until the user is on a pane that shows credentials or the exact
    /// permission grants this app depends on. The pane is only knowable from the window title.
    static let sensitiveSettingsPanes = [
        "password", "privacy", "security", "touch id", "users & groups", "login",
    ]

    static func isExcluded(appName: String, bundleID: String) -> Bool {
        if let own = Bundle.main.bundleIdentifier, bundleID == own { return true }
        if excludedBundleIdentifiers.contains(bundleID) { return true }
        let name = appName.lowercased()
        return excludedNameFragments.contains { name.contains($0) }
    }

    static func isSensitiveSettingsWindow(bundleID: String, title: String?) -> Bool {
        guard settingsBundleIdentifiers.contains(bundleID) else { return false }
        guard let title = title?.lowercased() else { return false }
        return sensitiveSettingsPanes.contains { title.contains($0) }
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

    static func process(_ captured: CapturedImage, capturedAt: Double) -> ProcessedFrame {
        // Detached tasks run on the cooperative pool, which does not drain autorelease pools; the
        // CoreGraphics and Vision temporaries below would otherwise accumulate for the app's life.
        autoreleasepool {
            let text = recognizeText(in: captured.image)
            let path = writeJPEG(captured.image, capturedAt: capturedAt)
            return ProcessedFrame(ocrText: text, imagePath: path)
        }
    }

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
        return sink.lines.joined(separator: "\n")
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
