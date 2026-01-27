import AppKit
import CoreGraphics
import Foundation
import ScreenCaptureKit

class ScreenCaptureService {
    private let maxSize: CGFloat = 1024
    private let jpegQuality: CGFloat = 0.85

    init() {}

    /// Check if we have screen recording permission
    static func checkPermission() -> Bool {
        // Always return true - let capture fail if no permission
        // This avoids unreliable permission checks on newer macOS
        return true
    }

    /// Open System Preferences to Screen Recording settings
    static func openScreenRecordingPreferences() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture") {
            NSWorkspace.shared.open(url)
        }
    }

    /// Get the window ID of the frontmost application's main window
    private static func getActiveWindowID() -> CGWindowID? {
        let (_, _, windowID) = getActiveWindowInfo()
        return windowID
    }

    /// Get the active app name, window title, and window ID
    static func getActiveWindowInfo() -> (appName: String?, windowTitle: String?, windowID: CGWindowID?) {
        guard let frontApp = NSWorkspace.shared.frontmostApplication else {
            return (nil, nil, nil)
        }

        let appName = frontApp.localizedName
        let activePID = frontApp.processIdentifier

        // Get all on-screen windows
        guard let windowList = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else {
            return (appName, nil, nil)
        }

        // Find the first window belonging to the active app
        for window in windowList {
            guard let windowPID = window[kCGWindowOwnerPID as String] as? Int32,
                  windowPID == activePID else {
                continue
            }

            // Skip windows that are too small (like menu bar items)
            if let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
               let width = bounds["Width"],
               let height = bounds["Height"],
               width > 100 && height > 100,
               let windowNumber = window[kCGWindowNumber as String] as? CGWindowID {
                let windowTitle = window[kCGWindowName as String] as? String
                return (appName, windowTitle, windowNumber)
            }
        }

        return (appName, nil, nil)
    }

    // MARK: - Async Capture (Primary API)

    /// Async capture - main entry point
    func captureActiveWindowAsync() async -> Data? {
        guard let windowID = Self.getActiveWindowID() else {
            log("No active window ID found")
            return nil
        }

        log("Capturing window ID: \(windowID)")

        if #available(macOS 14.0, *) {
            return await captureWithScreenCaptureKit(windowID: windowID)
        } else {
            // Fallback: run screencapture on background thread for macOS 13.x
            return await captureWithScreencaptureAsync(windowID: windowID)
        }
    }

    /// Capture using ScreenCaptureKit (macOS 14.0+)
    @available(macOS 14.0, *)
    private func captureWithScreenCaptureKit(windowID: CGWindowID) async -> Data? {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(
                false,
                onScreenWindowsOnly: true
            )

            guard let window = content.windows.first(where: { $0.windowID == windowID }) else {
                log("Window not found in SCShareableContent")
                return nil
            }

            let filter = SCContentFilter(desktopIndependentWindow: window)
            let config = SCStreamConfiguration()
            config.scalesToFit = true
            config.width = Int(min(window.frame.width, maxSize))
            config.height = Int(min(window.frame.height, maxSize))

            let image = try await SCScreenshotManager.captureImage(
                contentFilter: filter,
                configuration: config
            )

            return jpegData(from: image)
        } catch {
            log("ScreenCaptureKit error: \(error)")
            return nil
        }
    }

    /// Async wrapper for screencapture CLI (macOS 13.x fallback)
    private func captureWithScreencaptureAsync(windowID: CGWindowID) async -> Data? {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let result = self.captureWithScreencapture(windowID: windowID)
                continuation.resume(returning: result)
            }
        }
    }

    // MARK: - Synchronous Capture (Legacy)

    /// Capture the active window and return as JPEG data (synchronous - legacy)
    func captureActiveWindow() -> Data? {
        guard let windowID = Self.getActiveWindowID() else {
            log("No active window ID found")
            return nil
        }

        log("Capturing window ID: \(windowID)")
        // Use screencapture CLI (works on all macOS versions)
        return captureWithScreencapture(windowID: windowID)
    }

    /// Capture window using screencapture CLI
    private func captureWithScreencapture(windowID: CGWindowID) -> Data? {
        let tempPath = NSTemporaryDirectory() + "omi_capture_\(UUID().uuidString).jpg"

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        process.arguments = ["-l", String(windowID), "-x", "-o", tempPath]

        do {
            try process.run()
            process.waitUntilExit()

            if process.terminationStatus != 0 {
                log("screencapture failed with exit code: \(process.terminationStatus)")
                return nil
            }

            let data = try Data(contentsOf: URL(fileURLWithPath: tempPath))
            try? FileManager.default.removeItem(atPath: tempPath)

            // Load, resize if needed, and re-encode
            guard let nsImage = NSImage(data: data) else {
                return nil
            }

            var finalImage = nsImage
            let size = nsImage.size
            if max(size.width, size.height) > maxSize {
                let ratio = maxSize / max(size.width, size.height)
                let newSize = NSSize(width: size.width * ratio, height: size.height * ratio)
                finalImage = resizeImage(nsImage, to: newSize)
            }

            return jpegData(from: finalImage)

        } catch {
            try? FileManager.default.removeItem(atPath: tempPath)
            return nil
        }
    }

    // MARK: - Image Processing

    /// Resize an NSImage to the specified size
    private func resizeImage(_ image: NSImage, to newSize: NSSize) -> NSImage {
        let newImage = NSImage(size: newSize)
        newImage.lockFocus()
        NSGraphicsContext.current?.imageInterpolation = .high
        image.draw(
            in: NSRect(origin: .zero, size: newSize),
            from: NSRect(origin: .zero, size: image.size),
            operation: .copy,
            fraction: 1.0
        )
        newImage.unlockFocus()
        return newImage
    }

    /// Convert CGImage to JPEG data
    private func jpegData(from cgImage: CGImage) -> Data? {
        let nsImage = NSImage(cgImage: cgImage, size: NSSize(
            width: cgImage.width,
            height: cgImage.height
        ))
        return jpegData(from: nsImage)
    }

    /// Convert NSImage to JPEG data
    private func jpegData(from image: NSImage) -> Data? {
        guard let tiffData = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiffData) else {
            return nil
        }

        return bitmap.representation(
            using: .jpeg,
            properties: [.compressionFactor: jpegQuality]
        )
    }
}
