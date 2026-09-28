import AppKit
import CoreGraphics
import Foundation
import OmiKit
import OmiUI
import ScreenCaptureKit

// The macOS Rewind capture engine — the native `OmiRewind` module contract
// from the RN tree: Screen Recording permission probes, a real ScreenCaptureKit
// stream writing one JPEG frame per capture tick into Application Support,
// single-frame grabs, and retention pruning. While running, frames land in
// `Application Support/Omi v5/Rewind/<epoch-ms>.jpg` for the Rewind surface.
// The AppStore drives start/stop through the `RewindCaptureControlling`
// bridge when the `screenAnalysisEnabled` preference toggles.

final class OmiRewindEngine: @unchecked Sendable {
    static let shared = OmiRewindEngine()

    /// The AppStore bridge (permission probes + explicit start/stop/frame).
    let bridge: RewindCaptureControlling

    private let lock = NSLock()
    private var stream: SCStream?
    private var output: FrameOutput?
    private var ciContext: CIContext?
    private let frameDirectory: URL

    private init() {
        let base =
            FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first ?? FileManager.default.temporaryDirectory
        frameDirectory = base.appendingPathComponent("Omi v5/Rewind", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: frameDirectory, withIntermediateDirectories: true)
        bridge = RewindCaptureControlling(
            permissionStatus: { await OmiRewindEngine.shared.permissionStatus() },
            requestPermission: { await OmiRewindEngine.shared.requestPermission() },
            start: { try await OmiRewindEngine.shared.startCapture() },
            stop: { try await OmiRewindEngine.shared.stopCapture() },
            captureFrame: { await OmiRewindEngine.shared.captureFrame() })
        pruneExpiredFrames()
    }

    // MARK: Permission (native `requestCapturePermission` outcomes)

    func permissionStatus() async -> RewindCapturePermission {
        CGPreflightScreenCaptureAccess() ? .granted : .denied
    }

    func requestPermission() async -> RewindCapturePermission {
        if CGRequestScreenCaptureAccess() { return .granted }
        // The prompt may already have resolved; preflight again.
        return CGPreflightScreenCaptureAccess() ? .granted : .denied
    }

    // MARK: Capture session

    func startCapture() async throws {
        lock.lock()
        let existing = stream
        lock.unlock()
        guard existing == nil else { return }
        let content = try await SCShareableContent.excludingDesktopWindows(
            false, onScreenWindowsOnly: true)
        guard let display = content.displays.first else {
            throw OmiRewindError.noDisplay
        }
        let filter = SCContentFilter(display: display, excludingWindows: [])
        var configuration = SCStreamConfiguration()
        // One frame per capture tick (3 s in useRewindCapture.ts).
        configuration.minimumFrameInterval = CMTime(
            value: rewindCaptureTickMs, timescale: 1_000)
        configuration.width = max(2, Int(display.width))
        configuration.height = max(2, Int(display.height))
        configuration.showsCursor = true
        configuration.queueDepth = 3
        let output = FrameOutput(engine: self)
        let stream = SCStream(filter: filter, configuration: configuration, delegate: nil)
        try stream.addStreamOutput(output, type: .screen, sampleHandlerQueue: output.queue)
        try await stream.startCapture()
        lock.lock()
        self.stream = stream
        self.output = output
        lock.unlock()
    }

    func stopCapture() async throws {
        lock.lock()
        let stream = self.stream
        self.stream = nil
        self.output = nil
        lock.unlock()
        guard let stream else { return }
        try await stream.stopCapture()
    }

    /// Grabs one frame; returns whether a frame was actually captured.
    func captureFrame() async -> Bool {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(
                false, onScreenWindowsOnly: true)
            guard let display = content.displays.first else { return false }
            let filter = SCContentFilter(display: display, excludingWindows: [])
            var configuration = SCStreamConfiguration()
            configuration.width = max(2, Int(display.width))
            configuration.height = max(2, Int(display.height))
            configuration.showsCursor = true
            let image = try await SCScreenshotManager.captureImage(
                contentFilter: filter, configuration: configuration)
            return writeJPEG(cgImage: image)
        } catch {
            return false
        }
    }

    // MARK: Frame writing

    /// Writes one captured sample buffer as a timestamped JPEG. Called on
    /// the output queue.
    fileprivate func writeFrame(_ sampleBuffer: CMSampleBuffer) {
        guard sampleBuffer.isValid, let pixelBuffer = sampleBuffer.imageBuffer else {
            return
        }
        let context: CIContext
        lock.lock()
        if ciContext == nil { ciContext = CIContext(options: nil) }
        context = self.ciContext ?? CIContext(options: nil)
        lock.unlock()
        let image = CIImage(cvPixelBuffer: pixelBuffer)
        guard let cgImage = context.createCGImage(image, from: image.extent) else {
            return
        }
        _ = writeJPEG(cgImage: cgImage)
    }

    private func writeJPEG(cgImage: CGImage) -> Bool {
        let representation = NSBitmapImageRep(cgImage: cgImage)
        guard
            let jpeg = representation.representation(
                using: .jpeg, properties: [.compressionFactor: 0.72])
        else { return false }
        let stamp = Int64(Date().timeIntervalSince1970 * 1000)
        let url = frameDirectory.appendingPathComponent("\(stamp).jpg")
        do {
            try jpeg.write(to: url)
            writeFrameMeta(stamp: stamp)
            return true
        } catch {
            return false
        }
    }

    /// One JSON sidecar per frame with the frontmost app + window title —
    /// the metadata the RN native module stored alongside each capture
    /// (`RewindFrame.appName` / `.windowTitle`).
    private func writeFrameMeta(stamp: Int64) {
        var app = ""
        var title = ""
        if let front = NSWorkspace.shared.frontmostApplication {
            app = front.localizedName ?? ""
            title = WindowTitleReader.frontmostTitle(bundleIdentifier: front.bundleIdentifier) ?? ""
        }
        let meta = FrameMeta(appName: app, windowTitle: title)
        guard let data = try? JSONEncoder().encode(meta) else { return }
        try? data.write(to: frameDirectory.appendingPathComponent("\(stamp).json"))
    }

    // MARK: History reader (native `OmiRewind.listFrames` / `readFrame`)

    /// Newest-first frame page over the local capture store. `query`
    /// filters by app name + window title (case-insensitive); `cursor` is
    /// the previous page's last stamp.
    func frames(
        source: RewindSourceKind, query: String, cursor: String?, limit: Int
    ) throws -> RewindFramePage {
        // The shipping-history source needs the old Omi account store, which
        // the native capture engine does not carry — honestly unavailable.
        guard source == .captured else {
            throw RewindTimelineFailure.unavailable
        }
        let entries = readFrameEntries()
            .filter { entry in
                let needle = query.trimmingCharacters(in: .whitespaces).lowercased()
                guard !needle.isEmpty else { return true }
                return "\(entry.appName)\n\(entry.windowTitle)".lowercased()
                    .contains(needle)
            }
        // Cursor: skip until past the previous page's last (oldest) frame.
        var startIndex = 0
        if let cursor, let cursorStamp = Int(cursor) {
            startIndex =
                entries.firstIndex(where: { $0.stamp < cursorStamp }) ?? entries.count
        }
        let pageEntries = entries.dropFirst(startIndex).prefix(limit)
        let frames = pageEntries.map { entry in
            RewindFrame(
                id: "\(entry.stamp)", capturedAtMs: entry.stamp,
                appName: entry.appName, windowTitle: entry.windowTitle)
        }
        let nextCursor: String? =
            frames.count == limit ? pageEntries.last.map { "\($0.stamp)" } : nil
        return RewindFramePage(frames: frames, nextCursor: nextCursor)
    }

    /// `OmiRewind.readFrame` — the JPEG bytes for one frame id.
    func frameJPEG(id: String) -> Data? {
        try? Data(contentsOf: frameDirectory.appendingPathComponent("\(id).jpg"))
    }

    private func readFrameEntries() -> [(stamp: Int64, appName: String, windowTitle: String)] {
        let files = (try? FileManager.default.contentsOfDirectory(
            at: frameDirectory, includingPropertiesForKeys: nil)) ?? []
        var entries = [(stamp: Int64, appName: String, windowTitle: String)]()
        for file in files where file.pathExtension == "jpg" {
            guard let stamp = Int(file.deletingPathExtension().lastPathComponent) else {
                continue
            }
            let meta = (try? Data(contentsOf: frameDirectory.appendingPathComponent("\(stamp).json")))
                .flatMap { try? JSONDecoder().decode(FrameMeta.self, from: $0) }
            entries.append((Int64(stamp), meta?.appName ?? "", meta?.windowTitle ?? ""))
        }
        // Newest first (rewindTimeline.ts contract).
        return entries.sorted { $0.stamp > $1.stamp }
    }

    /// Applies the `rewindRetentionDays` preference on launch.
    private func pruneExpiredFrames() {
        let days = UserDefaults.standard.integer(forKey: "rewindRetentionDays")
        let retentionDays = days > 0 ? days : 30
        let cutoff = Date().addingTimeInterval(-Double(retentionDays) * 86_400)
        let files = (try? FileManager.default.contentsOfDirectory(
            at: frameDirectory, includingPropertiesForKeys: nil)) ?? []
        for file in files {
            guard let stamp = Int(file.deletingPathExtension().lastPathComponent),
                Date(timeIntervalSince1970: Double(stamp) / 1000) < cutoff
            else { continue }
            try? FileManager.default.removeItem(at: file)
        }
    }
}

/// Per-frame metadata sidecar (`<stamp>.json`).
private struct FrameMeta: Codable {
    var appName: String
    var windowTitle: String
}

/// Reads the frontmost window's title via the accessibility API (the same
/// source the RN `OmiRewind` module used for window labels).
enum WindowTitleReader {
    static func frontmostTitle(bundleIdentifier: String?) -> String? {
        guard let list = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
            as? [[String: Any]]
        else { return nil }
        for window in list {
            guard let layer = window["kCGWindowLayer"] as? Int, layer == 0,
                let bounds = window["kCGWindowBounds"] as? [String: Any],
                (bounds["Width"] as? Int ?? 0) > 60,
                (bounds["Height"] as? Int ?? 0) > 60
            else { continue }
            // Prefer a window of the frontmost application; the window list
            // is front-to-back, so the first owned layer-0 window is it.
            if let owner = window["kCGWindowOwnerName"] as? String,
                let front = NSWorkspace.shared.frontmostApplication,
                owner == front.localizedName
            {
                let title = window["kCGWindowName"] as? String
                return title ?? ""
            }
        }
        return nil
    }
}

enum OmiRewindError: Error {
    case noDisplay
}

/// The SCStream output: every screen sample becomes a JPEG frame.
private final class FrameOutput: NSObject, SCStreamOutput, @unchecked Sendable {
    let queue = DispatchQueue(label: "omi.v5.rewind-frames")
    private weak var engine: OmiRewindEngine?

    init(engine: OmiRewindEngine) {
        self.engine = engine
        super.init()
    }

    func stream(
        _ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
        of type: SCStreamOutputType
    ) {
        guard type == .screen, let engine else { return }
        engine.writeFrame(sampleBuffer)
    }
}
