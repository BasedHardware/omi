import SwiftUI

/// ToolbarItem without the macOS 26 shared glass platter. Bare glyphs fit
/// the app's dark custom surface; floating glass capsules read as foreign
/// against it. Older toolbars have no platters, so the plain item is
/// already correct there.
struct PlainToolbarItem<Content: View>: ToolbarContent {
    let placement: ToolbarItemPlacement
    @ViewBuilder let content: () -> Content

    init(placement: ToolbarItemPlacement = .automatic, @ViewBuilder content: @escaping () -> Content) {
        self.placement = placement
        self.content = content
    }

    var body: some ToolbarContent {
        #if compiler(>=6.2)
            if #available(macOS 26.0, *) {
                ToolbarItem(placement: placement, content: content)
                    .sharedBackgroundVisibility(.hidden)
            } else {
                ToolbarItem(placement: placement, content: content)
            }
        #else
            ToolbarItem(placement: placement, content: content)
        #endif
    }
}

/// Capture/Listening status controls and the settings menu for the native
/// window toolbar. Toolbar-scale, icon-first, system-styled — state reads
/// through symbol tint plus a small status dot, details live in tooltips.
struct ToolbarStatusControls: View {
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
            ToolbarStatusButton(
                systemImage: "inset.filled.rectangle.badge.record",
                title: "Capture",
                state: captureDotState,
                action: controls.toggleCapture,
                helpText: captureHelp
            )
            .disabled(controls.isTogglingCapture)

            ToolbarStatusButton(
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

            Menu {
                Button("Settings…") { navigate(to: .settings) }
                Divider()
                Button("Refer a Friend") { Self.openReferFriend() }
                Button("Join Discord") { Self.openDiscord() }
            } label: {
                Image(systemName: "gearshape")
            }
            // The app's root purple tint must not color toolbar glyphs —
            // native macOS toolbars use neutral symbols. Menu labels render
            // as template images driven by tint, so override tint itself.
            .tint(Color.secondary)
            .menuIndicator(.hidden)
            .help("Settings")
        }
        .onAppear { controls.syncCaptureState() }
    }

    private var captureDotState: ToolbarStatusButton.DotState {
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

    static func openReferFriend() {
        if let url = URL(string: "https://affiliate.omi.me") {
            NSWorkspace.shared.open(url)
        }
    }

    static func openDiscord() {
        if let url = URL(string: "https://discord.com/invite/8MP3b9ymvx") {
            NSWorkspace.shared.open(url)
        }
    }
}

/// A labeled toolbar button whose running state shows as a small badge on
/// the glyph: green dot = running, amber triangle = needs attention,
/// nothing = off. The label says what the control is; the badge says how
/// it's doing.
struct ToolbarStatusButton: View {
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

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: systemImage)
                    .foregroundStyle(state == .off ? Color.secondary : Color.primary)
                    .overlay(alignment: .topTrailing) {
                        switch state {
                        case .active:
                            Circle()
                                .fill(.green)
                                .frame(width: 5, height: 5)
                                .offset(x: 4, y: -3)
                        case .attention:
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 7))
                                .foregroundStyle(.yellow)
                                .offset(x: 6, y: -4)
                        case .off:
                            EmptyView()
                        }
                    }
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(state == .off ? Color.secondary : Color.primary)
            }
        }
        .help(helpText)
    }
}
