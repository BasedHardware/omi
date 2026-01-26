import AppKit
import SwiftUI

/// A transparent, click-through window that displays the glow effect overlay
class GlowOverlayWindow: NSWindow {
    init(contentRect: NSRect) {
        super.init(
            contentRect: contentRect,
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )

        // Make window transparent and floating
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = false

        // Float above other windows but below screen saver
        self.level = .floating

        // Click-through - don't intercept any mouse events
        self.ignoresMouseEvents = true

        // Don't show in mission control or app switcher
        self.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]

        // No title bar behaviors
        self.isMovableByWindowBackground = false
        self.titlebarAppearsTransparent = true
        self.titleVisibility = .hidden

        // Disable window animations to prevent crashes when closing
        // while Core Animation transactions are in progress
        self.animationBehavior = .none
    }

    /// Update the window frame to match a target window's bounds
    func updateFrame(to rect: NSRect) {
        // Add padding for the glow effect to extend beyond the window
        let glowPadding: CGFloat = 30
        let expandedRect = rect.insetBy(dx: -glowPadding, dy: -glowPadding)
        self.setFrame(expandedRect, display: true)
    }
}
