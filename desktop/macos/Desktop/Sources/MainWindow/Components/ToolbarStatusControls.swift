import SwiftUI

/// Capture/Listening status controls shown inside the Home surface.
/// State reads through symbol tint and subtle capsule fill; details live in tooltips.
struct InAppStatusControls: View {
    let appState: AppState

    @ObservedObject private var appStateObserved: AppState
    @StateObject private var controls: CaptureListeningController

    init(appState: AppState) {
        self.appState = appState
        self.appStateObserved = appState
        _controls = StateObject(wrappedValue: CaptureListeningController(appState: appState))
    }

    var body: some View {
        HStack(spacing: 10) {
            InAppStatusButton(
                systemImage: "inset.filled.rectangle.badge.record",
                title: "Capture",
                state: captureDotState,
                action: controls.toggleCapture,
                helpText: captureHelp
            )
            .disabled(controls.isTogglingCapture)

            InAppStatusButton(
                systemImage: appStateObserved.isTranscribing ? "waveform" : "mic",
                title: "Listening",
                state: appStateObserved.isTranscribing ? .active : .off,
                action: controls.toggleListening,
                helpText: appStateObserved.isTranscribing
                    ? "Listening is on — click to stop (\(controls.listeningModeTitle))"
                    : "Listening is off — click to start"
            )
            .disabled(controls.isTogglingListening)
            .contextMenu {
                Button("Audio mode: \(controls.listeningModeTitle) — switch") {
                    controls.toggleListeningMode()
                }
            }

            InAppStatusButton(
                systemImage: "gearshape",
                title: "Settings",
                state: .off,
                action: { navigate(to: .settings) },
                helpText: "Settings"
            )
        }
        .onAppear { controls.syncCaptureState() }
    }

    private var captureDotState: InAppStatusButton.DotState {
        switch controls.captureStatus {
        case .active: return .active
        case .blocked: return .attention
        case .inactive: return .off
        }
    }

    private var captureHelp: String {
        switch controls.captureStatus {
        case .active: return "Screen capture is on — click to turn off"
        case .inactive: return "Screen capture is off — click to turn on"
        case .blocked: return "Screen capture is blocked — click to fix permissions"
        }
    }

    private func navigate(to item: SidebarNavItem) {
        NotificationCenter.default.post(
            name: .navigateToSidebarItem,
            object: nil,
            userInfo: ["rawValue": item.rawValue]
        )
    }

}

/// A labeled Home toggle whose state must be readable at a glance:
/// running = green-tinted capsule fill with a green glyph, needs attention =
/// amber-tinted fill with a warning badge, off = plain dimmed glyph.
struct InAppStatusButton: View {
    enum DotState {
        case active
        case attention
        case off
    }

    let systemImage: String
    let title: String
    let state: DotState
    let action: () -> Void
    let helpText: String

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: systemImage)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(glyphColor)
                    .overlay(alignment: .topTrailing) {
                        if state == .attention {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 7))
                                .foregroundStyle(.yellow)
                                .offset(x: 6, y: -4)
                        }
                    }
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(state == .off ? Color.secondary : Color.primary)
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(Capsule(style: .continuous).fill(backgroundFill))
            .contentShape(Capsule(style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .help(helpText)
    }

    private var glyphColor: Color {
        switch state {
        case .active: return HomePalette.green
        case .attention: return Color.primary
        case .off: return Color.secondary
        }
    }

    private var backgroundFill: Color {
        switch state {
        case .active: return HomePalette.green.opacity(0.16)
        case .attention: return Color.yellow.opacity(0.12)
        case .off: return isHovering ? Color.white.opacity(0.07) : Color.clear
        }
    }
}
