import Cocoa
import SwiftUI

/// Preview phase for glow demonstration
enum GlowDemoPhase {
    case none
    case focused
    case distracted
}

/// Observable object to manage demo window state
@MainActor
class GlowDemoState: ObservableObject {
    static let shared = GlowDemoState()
    @Published var phase: GlowDemoPhase = .none
}

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
        GlowDemoState.shared.phase = .none
        sharedWindow?.close()
        sharedWindow = nil
    }

    /// Returns the current window frame, or nil if not showing
    static var currentFrame: NSRect? {
        return sharedWindow?.frame
    }

    /// Updates the preview phase
    static func setPhase(_ phase: GlowDemoPhase) {
        GlowDemoState.shared.phase = phase
    }

    private init() {
        // Window size for demo content
        let contentRect = NSRect(x: 0, y: 0, width: 340, height: 220)

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
        let hostingView = NSHostingView(rootView: demoView.withFontScaling())
        self.contentView = hostingView
    }
}

/// Content view for the demo window showing focused/distracted states
struct GlowDemoContentView: View {
    @ObservedObject private var state = GlowDemoState.shared

    var body: some View {
        VStack(spacing: 16) {
            // Preview content
            HStack(spacing: 20) {
                // Focused state
                glowStatePreview(
                    title: "Focused",
                    description: "You're on track",
                    color: Color(red: 0.16, green: 0.79, blue: 0.26),
                    isActive: state.phase == .focused
                )

                // Arrow between states
                Image(systemName: "arrow.right")
                    .scaledFont(size: 16, weight: .medium)
                    .foregroundColor(.secondary.opacity(0.5))

                // Distracted state
                glowStatePreview(
                    title: "Distracted",
                    description: "Time to refocus",
                    color: Color(red: 0.95, green: 0.3, blue: 0.3),
                    isActive: state.phase == .distracted
                )
            }
            .padding(.vertical, 8)

            // Progress indicator
            HStack(spacing: 8) {
                if state.phase != .none {
                    ProgressView()
                        .scaleEffect(0.6)
                    Text(state.phase == .focused ? "Showing focused glow..." : "Showing distracted glow...")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                } else {
                    Text("Watch the border effect")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary.opacity(0.6))
                }
            }
            .frame(height: 20)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: .windowBackgroundColor))
    }

    private func glowStatePreview(title: String, description: String, color: Color, isActive: Bool) -> some View {
        VStack(spacing: 8) {
            // Glow indicator circle
            ZStack {
                // Outer glow
                Circle()
                    .fill(color.opacity(isActive ? 0.3 : 0.1))
                    .frame(width: 50, height: 50)
                    .blur(radius: isActive ? 8 : 0)

                // Inner circle
                Circle()
                    .fill(color.opacity(isActive ? 1.0 : 0.3))
                    .frame(width: 30, height: 30)

                // Pulse animation
                if isActive {
                    Circle()
                        .stroke(color.opacity(0.5), lineWidth: 2)
                        .frame(width: 40, height: 40)
                        .scaleEffect(isActive ? 1.3 : 1.0)
                        .opacity(isActive ? 0 : 1)
                        .animation(
                            Animation.easeOut(duration: 1.0).repeatForever(autoreverses: false),
                            value: isActive
                        )
                }
            }
            .frame(width: 60, height: 60)

            // Labels
            Text(title)
                .scaledFont(size: 13, weight: isActive ? .semibold : .regular)
                .foregroundColor(isActive ? .primary : .secondary)

            Text(description)
                .scaledFont(size: 11)
                .foregroundColor(.secondary.opacity(0.8))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(isActive ? color.opacity(0.1) : Color.clear)
        )
        .animation(.easeInOut(duration: 0.3), value: isActive)
    }
}
