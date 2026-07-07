import AppKit
import SwiftUI

/// The consistent page header: optional home affordance + serif page title
/// on the left, the Capture/Listening pills and settings menu on the right —
/// the same control cluster the Home header established, available to every
/// main page.
struct PageHeaderView: View {
    /// nil hides the title (Home shows only the trailing cluster).
    var title: String? = nil
    /// Shows the "back to Home" chip on non-Home pages.
    var showsHomeButton = false
    let appState: AppState

    @ObservedObject private var appStateObserved: AppState
    @StateObject private var controls: CaptureListeningController

    init(title: String? = nil, showsHomeButton: Bool = false, appState: AppState) {
        self.title = title
        self.showsHomeButton = showsHomeButton
        self.appState = appState
        self.appStateObserved = appState
        _controls = StateObject(wrappedValue: CaptureListeningController(appState: appState))
    }

    var body: some View {
        HStack(spacing: 12) {
            if showsHomeButton {
                PageHeaderHomeButton {
                    Self.navigate(to: .dashboard)
                }
            }

            if let title {
                Text(title)
                    .font(.system(size: 20, weight: .medium, design: .serif))
                    .foregroundStyle(Color.white.opacity(0.92))
            }

            Spacer()

            HStack(spacing: 10) {
                HomeStatusButton(
                    title: "Capture",
                    systemImage: "viewfinder",
                    status: controls.captureStatus,
                    isToggling: controls.isTogglingCapture,
                    action: controls.toggleCapture
                )

                HomeListeningStatusButton(
                    title: "Listening",
                    systemImage: appStateObserved.isTranscribing
                        ? "waveform.circle.fill" : "mic.circle",
                    status: appStateObserved.isTranscribing ? .active : .inactive,
                    modeTitle: controls.listeningModeTitle,
                    isMeetingsOnly: controls.listeningCaptureMode == .onlyDuringMeetings,
                    isToggling: controls.isTogglingListening,
                    action: controls.toggleListening,
                    modeAction: controls.toggleListeningMode
                )

                HomeSettingsMenuButton(
                    onRefer: Self.openReferFriend,
                    onDiscord: Self.openDiscord,
                    onSettings: { Self.navigate(to: .settings) }
                )
            }
        }
        .frame(height: 36)
        .onAppear { controls.syncCaptureState() }
    }

    // MARK: - Shared actions

    private static func navigate(to item: SidebarNavItem) {
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

/// Rounded "back to Home" chip, styled to sit beside the header pills.
private struct PageHeaderHomeButton: View {
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: "house.fill")
                    .scaledFont(size: 11, weight: .medium)
                Text("Home")
                    .scaledFont(size: 12, weight: .medium)
            }
            .foregroundStyle(Color.white.opacity(isHovering ? 0.95 : 0.7))
            .padding(.horizontal, 12)
            .frame(height: 30)
            .background(
                Capsule().fill(Color.white.opacity(isHovering ? 0.12 : 0.06))
            )
            .overlay(
                Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1)
            )
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .help("Back to Home")
        .keyboardShortcut("[", modifiers: .command)
    }
}
