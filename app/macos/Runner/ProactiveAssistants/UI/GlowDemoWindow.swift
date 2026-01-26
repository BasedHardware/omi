import Cocoa
import SwiftUI

/// A small demo window used to preview the glow effect
class GlowDemoWindow: NSWindow {
    private static var sharedWindow: GlowDemoWindow?

    /// Shows the demo window centered on screen
    static func show() -> GlowDemoWindow {
        if let existing = sharedWindow {
            existing.makeKeyAndOrderFront(nil)
            return existing
        }

        let window = GlowDemoWindow()
        sharedWindow = window
        window.makeKeyAndOrderFront(nil)
        return window
    }

    /// Closes the demo window
    static func close() {
        sharedWindow?.close()
        sharedWindow = nil
    }

    /// Returns the current window frame, or nil if not showing
    static var currentFrame: NSRect? {
        return sharedWindow?.frame
    }

    private init() {
        // Small window size for demo
        let contentRect = NSRect(x: 0, y: 0, width: 300, height: 200)

        super.init(
            contentRect: contentRect,
            styleMask: [.titled, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )

        self.title = "Glow Preview"
        self.titlebarAppearsTransparent = true
        self.isMovableByWindowBackground = true
        self.isReleasedWhenClosed = false
        self.level = .floating

        // Center on screen
        self.center()

        // Create demo content
        let demoView = GlowDemoContentView()
        let hostingView = NSHostingView(rootView: demoView)
        self.contentView = hostingView
    }
}

/// Simple content view for the demo window
struct GlowDemoContentView: View {
    var body: some View {
        VStack(spacing: 16) {
            Spacer()

            Image(systemName: "sparkles")
                .font(.system(size: 40))
                .foregroundColor(.accentColor)

            Text("Glow Preview")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(.primary)

            Text("Watch the border effect")
                .font(.system(size: 13))
                .foregroundColor(.secondary)

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: .windowBackgroundColor))
    }
}
