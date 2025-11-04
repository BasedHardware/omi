import Cocoa
import SwiftUI

// MARK: - SwiftUI Views

/// A view that wraps `NSVisualEffectView` for use in SwiftUI.
private struct ControlBarVisualEffectView: NSViewRepresentable {
    var material: NSVisualEffectView.Material
    var blendingMode: NSVisualEffectView.BlendingMode

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
    }
}

/// A view for displaying a keyboard key.
private struct KeyView: View {
    var key: String
    var body: some View {
        let keyContent = Text(key)
            .font(.system(size: 12, weight: .regular))
            .foregroundColor(.white)
            .padding(.horizontal, 6)
            .frame(height: 24)
            .frame(minWidth: 24)

        keyContent
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .strokeBorder(Color.white.opacity(0.3), lineWidth: 0.5)
            )
    }
}

/// A custom button style for command buttons.
private struct CommandButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .cornerRadius(8)
            .scaleEffect(configuration.isPressed ? 0.95 : 1.0)
            .opacity(configuration.isPressed ? 0.8 : 1.0)
            .animation(.easeInOut(duration: 0.1), value: configuration.isPressed)
    }
}

/// A view for a button that displays a command and its keyboard shortcut.
private struct CommandButton: View {
    var title: String
    var keys: [String]
    var action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Text(title)
                    .font(.system(size: 14, weight: .regular))
                    .foregroundColor(.white)

                ForEach(keys, id: \.self) { key in
                    KeyView(key: key)
                }
            }
        }
        .buttonStyle(CommandButtonStyle())
        .scaleEffect(isHovered ? 1.05 : 1.0)
        .animation(.easeInOut(duration: 0.15), value: isHovered)
        .onHover { hovering in
            isHovered = hovering
        }
    }
}

/// A spinning loading indicator.
private struct SpinnerView: View {
    @State private var isSpinning = false

    var body: some View {
        Image("app_launcher_icon")
            .resizable()
            .frame(width: 24, height: 24)
            .foregroundColor(.black)
            .rotationEffect(.degrees(isSpinning ? 360 : 0))
            .animation(.linear(duration: 1).repeatForever(autoreverses: false), value: isSpinning)
            .scaleEffect(0.9)  // Slightly smaller for better visual balance
            .opacity(0.9)  // Slightly transparent to indicate loading state
            .onAppear {
                withAnimation {
                    isSpinning = true
                }
            }
    }
}

/// A vertical separator line.
private struct Separator: View {
    var body: some View {
        Rectangle()
            .fill(Color.white.opacity(0.0))
            .frame(width: 8, height: 20)
    }
}

/// A view modifier for the main background of the control bar.
private struct MainBackgroundStyle: ViewModifier {
    let cornerRadius: CGFloat

    func body(content: Content) -> some View {
        content
            .background(
                ControlBarVisualEffectView(material: .menu, blendingMode: .withinWindow)
                    .opacity(0.7)
                    .cornerRadius(cornerRadius)
            )
    }
}

/// The main SwiftUI view for the floating control bar.
private struct FloatingControlBarView: View {
    @EnvironmentObject var state: FloatingControlBarState

    // Callbacks
    var onPlayPause: () -> Void
    var onAskAI: () -> Void
    var onHide: () -> Void

    private var formattedDuration: String {
        let minutes = state.duration / 60
        let seconds = state.duration % 60
        return String(format: "%02d:%02d", minutes, seconds)
    }

    private var playPauseIcon: String {
        return (state.isRecording && !state.isPaused) ? "pause.fill" : "play.fill"
    }

    var body: some View {
        HStack(spacing: 12) {
            // Recording status
            HStack(spacing: 8) {
                Button(action: onPlayPause) {
                    Group {
                        if state.isInitialising {
                            SpinnerView()
                                .frame(width: 28, height: 28)
                                .background(Color.white)
                                .clipShape(Circle())
                        } else {
                            Image(systemName: playPauseIcon)
                                .font(.system(size: 12, weight: .bold))
                                .frame(width: 28, height: 28)
                                .foregroundColor(.black)
                                .background(Color.white)
                                .clipShape(Circle())
                                .scaleEffect(state.isRecording && !state.isPaused ? 1.0 : 0.9)
                        }
                    }
                }
                .buttonStyle(.plain)

                // Animated timer with smooth transitions
                if state.isRecording {
                    Text(formattedDuration)
                        .font(.system(size: 14, weight: .regular).monospacedDigit())
                        .foregroundColor(.white)
                        .transition(
                            .asymmetric(
                                insertion: .scale(scale: 0.8).combined(with: .opacity),
                                removal: .scale(scale: 0.8).combined(with: .opacity)
                            )
                        )
                        .animation(.easeInOut(duration: 0.3), value: state.duration)
                }
            }

            Separator()

            CommandButton(title: "Ask Omi", keys: ["⌘", "K"], action: onAskAI)

            Separator()

            CommandButton(title: "Show/Hide", keys: ["⌘", "\\"], action: onHide)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(width: 400, height: 56)
        .modifier(MainBackgroundStyle(cornerRadius: 20))
    }
}

// MARK: - AppKit Integration

/// An observable object to hold the state for the floating control bar.
private class FloatingControlBarState: ObservableObject {
    @Published var isRecording: Bool = false
    @Published var isPaused: Bool = false
    @Published var duration: Int = 0
    @Published var isInitialising: Bool = false
}

/// The `NSWindow` subclass that hosts the SwiftUI control bar.
class FloatingControlBar: NSWindow, NSWindowDelegate {
    private static let positionKey = "FloatingControlBarPosition"

    // Callbacks for button actions
    var onPlayPause: (() -> Void)?
    var onAskAI: (() -> Void)?
    var onHide: (() -> Void)?
    var onMove: (() -> Void)?
    var onResize: ((CGFloat) -> Void)?

    private var state = FloatingControlBarState()
    private var hostingView: NSHostingView<AnyView>?

    override init(
        contentRect: NSRect, styleMask style: NSWindow.StyleMask,
        backing backingStoreType: NSWindow.BackingStoreType = .buffered, defer flag: Bool = false
    ) {
        super.init(
            contentRect: contentRect, styleMask: [.borderless, .utilityWindow], backing: backingStoreType,
            defer: flag)

        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = false
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.isMovableByWindowBackground = true
        self.delegate = self

        setupViews()

        if let savedPosition = UserDefaults.standard.string(forKey: FloatingControlBar.positionKey)
        {
            let origin = NSPointFromString(savedPosition)
            self.setFrameOrigin(origin)
        } else {
            self.center()
        }
    }

    // Allow the window to become the key window to receive keyboard events.
    override var canBecomeKey: Bool {
        return true
    }

    // Allow the window to become the main window.
    override var canBecomeMain: Bool {
        return true
    }

    private func setupViews() {
        let swiftUIView = FloatingControlBarView(
            onPlayPause: { [weak self] in self?.onPlayPause?() },
            onAskAI: { [weak self] in self?.onAskAI?() },
            onHide: { [weak self] in self?.hideClicked() }
        ).environmentObject(state)

        hostingView = NSHostingView(rootView: AnyView(swiftUIView))
        self.contentView = hostingView
        self.setContentSize(hostingView!.intrinsicContentSize)
    }

    private func hideClicked() {
        self.orderOut(nil)
        onHide?()
    }

    // --- Public Methods for State Update ---
    public func updateRecordingState(
        isRecording: Bool, isPaused: Bool, duration: Int, isInitialising: Bool
    ) {
        DispatchQueue.main.async {
            withAnimation(.easeInOut(duration: 0.35)) {
                self.state.isRecording = isRecording
                self.state.isPaused = isPaused
                self.state.duration = duration
                self.state.isInitialising = isInitialising
            }

            // Auto-resize window after animation
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                if let hostingView = self.hostingView {
                    let newSize = hostingView.intrinsicContentSize
                    self.setContentSize(newSize)
                }
            }
        }
    }

    public func resetPosition() {
        UserDefaults.standard.removeObject(forKey: FloatingControlBar.positionKey)
        self.center()
    }

    @objc func windowDidMove(_ notification: Notification) {
        UserDefaults.standard.set(
            NSStringFromPoint(self.frame.origin), forKey: FloatingControlBar.positionKey)
        onMove?()
    }
}
