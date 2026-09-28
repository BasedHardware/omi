import AppKit
import CoreGraphics
import Foundation
import OmiKit
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
        pruneExpiredFrames()
        bridge = RewindCaptureControlling(
            permissionStatus: { await OmiRewindEngine.shared.permissionStatus() },
            requestPermission: { await OmiRewindEngine.shared.requestPermission() },
            start: { try await OmiRewindEngine.shared.startCapture() },
            stop: { try await OmiRewindEngine.shared.stopCapture() },
            captureFrame: { await OmiRewindEngine.shared.captureFrame() })
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
            return true
        } catch {
            return false
        }
    }

    /// Applies the `rewindRetentionDays` preference on launch.
    private func pruneExpiredFrames() {
        let days = UserDefaults.standard.integer(forKey: "rewindRetentionDays")
        let retentionDays = days > 0 ? days : 30
        let cutoff = Date().addingTimeInterval(-Double(retentionDays) * 86_400)
        let files = (try? FileManager.default.contentsOfDirectory(
            at: frameDirectory, includingPropertiesForKeys: nil)) ?? []
        for file in files where file.pathExtension == "jpg" {
            if let stamp = Int(file.deletingPathExtension().lastPathComponent),
                Date(timeIntervalSince1970: Double(stamp) / 1000) < cutoff
            {
                try? FileManager.default.removeItem(at: file)
            }
        }
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
