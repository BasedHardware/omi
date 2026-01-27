import AppKit
import SwiftUI

/// Controller that manages the glow overlay window
@MainActor
class OverlayService {
    static let shared = OverlayService()

    private var overlayWindow: GlowOverlayWindow?
    private var dismissTask: Task<Void, Never>?

    private init() {}

    /// Show the glow effect around the currently active window
    /// - Parameter colorMode: The color mode for the glow (focused = green, distracted = red)
    func showGlowAroundActiveWindow(colorMode: GlowColorMode = .focused) {
        // Check if glow overlay is enabled in settings
        guard AssistantSettings.shared.glowOverlayEnabled else {
            log("Glow overlay disabled in settings, skipping")
            return
        }

        // Get the active window's frame
        guard let windowFrame = getActiveWindowFrame() else {
            log("Could not get active window frame for glow effect")
            return
        }

        showGlow(around: windowFrame, colorMode: colorMode)
    }

    /// Show the glow effect around a specific frame (used for preview)
    /// - Parameters:
    ///   - frame: The frame to show the glow around
    ///   - colorMode: The color mode for the glow (focused = green, distracted = red)
    ///   - isPreview: If true, bypasses the settings check (for preview mode)
    func showGlow(around frame: NSRect, colorMode: GlowColorMode, isPreview: Bool = false) {
        // Check if glow overlay is enabled in settings (unless this is a preview)
        if !isPreview {
            guard AssistantSettings.shared.glowOverlayEnabled else {
                log("Glow overlay disabled in settings, skipping")
                return
            }
        }

        // Dismiss any existing overlay
        dismissOverlay()

        // Create the overlay window
        let overlay = GlowOverlayWindow(contentRect: frame)

        // Create the SwiftUI glow view with the specified color mode
        let glowView = GlowBorderView(targetSize: frame.size, colorMode: colorMode)
        let hostingView = NSHostingView(rootView: glowView)
        hostingView.frame = overlay.contentView?.bounds ?? .zero
        hostingView.autoresizingMask = [.width, .height]

        overlay.contentView?.addSubview(hostingView)
        overlay.updateFrame(to: frame)

        // Show the window
        overlay.orderFrontRegardless()

        self.overlayWindow = overlay

        log("Showing \(colorMode == .focused ? "green" : "red") glow effect around window at \(frame)\(isPreview ? " (preview)" : "")")

        // Auto-dismiss after animation completes
        dismissTask = Task {
            do {
                try await Task.sleep(nanoseconds: 3_500_000_000) // 3.5 seconds
                await MainActor.run {
                    self.dismissOverlay()
                }
            } catch {
                // Task was cancelled (e.g., new glow shown before this one finished)
                // Don't dismiss - the new glow's task will handle dismissal
            }
        }
    }

    /// Dismiss the overlay window
    func dismissOverlay() {
        dismissTask?.cancel()
        dismissTask = nil

        // Remove the content view first to stop SwiftUI animations
        overlayWindow?.contentView?.subviews.forEach { $0.removeFromSuperview() }

        // Disable window animations to prevent use-after-free crash
        // The crash occurs when _NSWindowTransformAnimation tries to access
        // a deallocated window during autorelease pool drain
        overlayWindow?.animationBehavior = .none

        // Use orderOut instead of close to avoid triggering additional animations
        overlayWindow?.orderOut(nil)
        overlayWindow = nil
    }

    /// Get the frame of the currently active window
    private func getActiveWindowFrame() -> NSRect? {
        guard let frontApp = NSWorkspace.shared.frontmostApplication else {
            return nil
        }

        let activePID = frontApp.processIdentifier

        // Get all on-screen windows
        guard let windowList = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements],
            kCGNullWindowID
        ) as? [[String: Any]] else {
            return nil
        }

        // Find the first window belonging to the active app
        for window in windowList {
            guard let windowPID = window[kCGWindowOwnerPID as String] as? Int32,
                  windowPID == activePID else {
                continue
            }

            // Get window bounds
            if let boundsDict = window[kCGWindowBounds as String] as? [String: CGFloat],
               let x = boundsDict["X"],
               let y = boundsDict["Y"],
               let width = boundsDict["Width"],
               let height = boundsDict["Height"],
               width > 100 && height > 100 {

                // CGWindowList uses top-left origin, but NSWindow uses bottom-left
                // Convert coordinate system
                let screenHeight = NSScreen.main?.frame.height ?? 0
                let flippedY = screenHeight - y - height

                return NSRect(x: x, y: flippedY, width: width, height: height)
            }
        }

        return nil
    }
}

// MARK: - Backward Compatibility Alias

/// Alias for backward compatibility
typealias GlowOverlayController = OverlayService
