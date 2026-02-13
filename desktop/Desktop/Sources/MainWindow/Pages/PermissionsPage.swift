import SwiftUI
import AppKit
import AVFoundation

struct PermissionsPage: View {
    @ObservedObject var appState: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 28))
                            .foregroundColor(OmiColors.warning)

                        Text("Permissions Required")
                            .font(.system(size: 24, weight: .bold))
                            .foregroundColor(OmiColors.textPrimary)
                    }

                    Text("Omi needs the following permissions to work properly.")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textSecondary)
                }
                .padding(.bottom, 8)

                // Permission sections
                VStack(spacing: 20) {
                    // Microphone Permission
                    MicrophonePermissionSection(appState: appState)

                    // Screen Recording Permission
                    ScreenRecordingPermissionSection(appState: appState)

                    // Notification Permission
                    NotificationPermissionSection(appState: appState)
                }

                // All permissions granted message
                if !appState.hasMissingPermissions {
                    HStack(spacing: 12) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 20))
                            .foregroundColor(.green)

                        Text("All permissions granted! Omi is ready to use.")
                            .font(.system(size: 15, weight: .medium))
                            .foregroundColor(OmiColors.textPrimary)
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(Color.green.opacity(0.1))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.green.opacity(0.3), lineWidth: 1)
                            )
                    )
                }

                Spacer()
            }
            .padding(24)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.clear)
        .onAppear {
            appState.checkAllPermissions()
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            // Auto-refresh when app becomes active (user may have granted permission in System Settings)
            appState.checkAllPermissions()
        }
    }
}

// MARK: - Microphone Permission Section
struct MicrophonePermissionSection: View {
    @ObservedObject var appState: AppState
    @State private var isExpanded = true
    @State private var isResetting = false
    @State private var resetButtonText = "Reset & Restart"

    // Check if permission was explicitly denied (not just "not determined")
    private var isPermissionDenied: Bool {
        return appState.isMicrophonePermissionDenied()
    }

    // Colors based on state
    private var iconBackgroundColor: Color {
        if appState.hasMicrophonePermission {
            return Color.green.opacity(0.15)
        } else if isPermissionDenied {
            return Color.red.opacity(0.15)
        } else {
            return OmiColors.backgroundTertiary
        }
    }

    private var iconColor: Color {
        if appState.hasMicrophonePermission {
            return .green
        } else if isPermissionDenied {
            return .red
        } else {
            return OmiColors.textSecondary
        }
    }

    private var borderColor: Color {
        if appState.hasMicrophonePermission {
            return Color.green.opacity(0.3)
        } else if isPermissionDenied {
            return Color.red.opacity(0.5)
        } else {
            return OmiColors.backgroundQuaternary.opacity(0.5)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            Button(action: { withAnimation { isExpanded.toggle() } }) {
                HStack(spacing: 16) {
                    // Icon - pulsing animation when denied
                    ZStack {
                        Circle()
                            .fill(iconBackgroundColor)
                            .frame(width: 48, height: 48)

                        Image(systemName: isPermissionDenied ? "mic.slash.fill" : "mic.fill")
                            .font(.system(size: 22))
                            .foregroundColor(iconColor)
                    }

                    // Title and status
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 8) {
                            Text("Microphone")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(OmiColors.textPrimary)

                            microphoneStatusBadge
                        }

                        Text(isPermissionDenied
                            ? "Permission was denied - reset required"
                            : "Required for voice recording and transcription")
                            .font(.system(size: 13))
                            .foregroundColor(isPermissionDenied ? .red.opacity(0.8) : OmiColors.textTertiary)
                    }

                    Spacer()

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .padding(20)
            }
            .buttonStyle(.plain)

            // Expanded content - different for denied vs not determined
            if isExpanded && !appState.hasMicrophonePermission {
                VStack(alignment: .leading, spacing: 16) {
                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    if isPermissionDenied {
                        // DENIED STATE - Show reset options
                        deniedStateContent
                    } else {
                        // NOT DETERMINED - Show normal grant flow
                        notDeterminedStateContent
                    }
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 20)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(isPermissionDenied ? Color.red.opacity(0.05) : OmiColors.backgroundSecondary.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(borderColor, lineWidth: isPermissionDenied ? 2 : 1)
                )
        )
    }

    // Status badge for microphone
    private var microphoneStatusBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: appState.hasMicrophonePermission ? "checkmark.circle.fill" : (isPermissionDenied ? "xmark.circle.fill" : "exclamationmark.circle.fill"))
                .font(.system(size: 12))
            Text(appState.hasMicrophonePermission ? "Granted" : (isPermissionDenied ? "Denied" : "Not Granted"))
                .font(.system(size: 12, weight: .medium))
        }
        .foregroundColor(appState.hasMicrophonePermission ? .green : (isPermissionDenied ? .red : OmiColors.warning))
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            Capsule()
                .fill(appState.hasMicrophonePermission ? Color.green.opacity(0.15) : (isPermissionDenied ? Color.red.opacity(0.15) : OmiColors.warning.opacity(0.15)))
        )
    }

    // Content for DENIED state - shows reset options
    // Note: Grant Access button is NOT shown here because macOS won't show the permission
    // dialog again after the user denied it. They must reset the permission first.
    private var deniedStateContent: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Microphone access was previously denied. Reset the permission to try again:")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(OmiColors.textPrimary)

            // Option 1: Quick Reset
            VStack(alignment: .leading, spacing: 8) {
                Text("Option 1: Quick Reset")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                Button(action: tryDirectReset) {
                    HStack(spacing: 8) {
                        if isResetting {
                            ProgressView()
                                .scaleEffect(0.7)
                                .frame(width: 14, height: 14)
                        } else {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 14))
                        }
                        Text(resetButtonText)
                            .font(.system(size: 14, weight: .semibold))
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .frame(maxWidth: .infinity)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(isResetting ? Color.gray : OmiColors.purplePrimary)
                    )
                }
                .buttonStyle(.plain)
                .disabled(isResetting)
            }

            // Option 2: Terminal
            VStack(alignment: .leading, spacing: 8) {
                Text("Option 2: Reset via Terminal")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                Button(action: tryTerminalReset) {
                    HStack(spacing: 8) {
                        Image(systemName: "terminal")
                            .font(.system(size: 14))
                        Text("Open Terminal")
                            .font(.system(size: 14, weight: .semibold))
                    }
                    .foregroundColor(OmiColors.textPrimary)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .frame(maxWidth: .infinity)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(OmiColors.backgroundTertiary)
                    )
                }
                .buttonStyle(.plain)
            }

            // Option 3: Manual
            VStack(alignment: .leading, spacing: 12) {
                Text("Option 3: Manual")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                // Step 1: Open System Settings
                HStack(alignment: .top, spacing: 8) {
                    Text("1.")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(OmiColors.textSecondary)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Open System Settings")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textSecondary)

                        Button(action: openSystemSettings) {
                            HStack(spacing: 8) {
                                Image(systemName: "gear")
                                    .font(.system(size: 14))
                                Text("Open Privacy Settings")
                                    .font(.system(size: 14, weight: .semibold))
                            }
                            .foregroundColor(OmiColors.textPrimary)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(OmiColors.backgroundTertiary)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }

                // Step 2: Find Omi and toggle ON
                HStack(alignment: .top, spacing: 8) {
                    Text("2.")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(OmiColors.textSecondary)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Find \"Omi\" and toggle it ON")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textSecondary)

                        // Screenshot showing the toggle
                        if let image = NSImage(contentsOfFile: Bundle.resourceBundle.path(forResource: "microphone-settings", ofType: "png") ?? "") {
                            Image(nsImage: image)
                                .resizable()
                                .scaledToFit()
                                .frame(maxWidth: 300)
                                .cornerRadius(8)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(OmiColors.backgroundQuaternary, lineWidth: 1)
                                )
                        }
                    }
                }
            }
        }
    }

    // Content for NOT DETERMINED state - shows normal grant flow
    private var notDeterminedStateContent: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("How to grant microphone access:")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(OmiColors.textPrimary)

            VStack(alignment: .leading, spacing: 12) {
                instructionStep(number: 1, text: "Click \"Grant Access\" below - a system dialog will appear")
                instructionStep(number: 2, text: "Click \"OK\" to allow microphone access")
                instructionStep(number: 3, text: "If no dialog appears, find \"\(Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Omi")\" in Settings and enable it")
            }

            Button(action: {
                NSApp.activate(ignoringOtherApps: true)
                appState.requestMicrophonePermission()
            }) {
                HStack(spacing: 8) {
                    Image(systemName: "hand.tap.fill")
                        .font(.system(size: 14))
                    Text("Grant Access")
                        .font(.system(size: 14, weight: .semibold))
                }
                .foregroundColor(.white)
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(OmiColors.purplePrimary)
                )
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - Actions

    private func tryDirectReset() {
        isResetting = true
        resetButtonText = "Resetting & Restarting..."

        DispatchQueue.global(qos: .userInitiated).async {
            // Reset and restart the app - macOS requires restart to show permission dialog again
            let success = appState.resetMicrophonePermissionDirect(shouldRestart: true)

            if !success {
                DispatchQueue.main.async {
                    resetButtonText = "Failed - Try Option 2"
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                        isResetting = false
                        resetButtonText = "Reset & Restart"
                    }
                }
            }
            // If success, app will restart automatically
        }
    }

    private func tryTerminalReset() {
        // Reset via terminal and restart - macOS requires restart to show permission dialog again
        appState.resetMicrophonePermissionViaTerminal(shouldRestart: true)
    }

    private func openSystemSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone") {
            NSWorkspace.shared.open(url)
        }
        // User will manually grant permission in System Settings
        // No automatic restart needed - they can grant it directly there
    }
}

// MARK: - Screen Recording Permission Section
struct ScreenRecordingPermissionSection: View {
    @ObservedObject var appState: AppState
    @State private var isExpanded = true

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            Button(action: { withAnimation { isExpanded.toggle() } }) {
                HStack(spacing: 16) {
                    // Icon
                    ZStack {
                        Circle()
                            .fill(appState.hasScreenRecordingPermission ? Color.green.opacity(0.15) : OmiColors.backgroundTertiary)
                            .frame(width: 48, height: 48)

                        Image(systemName: "rectangle.inset.filled.and.person.filled")
                            .font(.system(size: 22))
                            .foregroundColor(appState.hasScreenRecordingPermission ? .green : OmiColors.textSecondary)
                    }

                    // Title and status
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 8) {
                            Text("Screen Recording")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(OmiColors.textPrimary)

                            statusBadge(isGranted: appState.hasScreenRecordingPermission)
                        }

                        Text("Required for proactive monitoring and context awareness")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .padding(20)
            }
            .buttonStyle(.plain)

            // Expanded content
            if isExpanded && !appState.hasScreenRecordingPermission {
                VStack(alignment: .leading, spacing: 16) {
                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    Text("How to grant screen recording access:")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(OmiColors.textPrimary)

                    VStack(alignment: .leading, spacing: 12) {
                        instructionStep(number: 1, text: "Click \"Open Settings\" below - this will make Omi appear in the list")
                        instructionStep(number: 2, text: "Find \"\(Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Omi")\" in the Screen Recording list")
                        instructionStep(number: 3, text: "Toggle the switch to enable screen recording")
                        instructionStep(number: 4, text: "Return to Omi - permission will update automatically")
                    }

                    // Tutorial GIF
                    AnimatedGIFView(gifName: "permissions")
                        .frame(maxWidth: 400, maxHeight: 300)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(OmiColors.backgroundQuaternary, lineWidth: 1)
                        )

                    Button(action: {
                        // First trigger screen capture to make app appear in list
                        appState.triggerScreenRecordingPermission()
                        // Then open System Settings after a brief delay
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                            ProactiveAssistantsPlugin.shared.openScreenRecordingPreferences()
                        }
                    }) {
                        HStack(spacing: 8) {
                            Image(systemName: "gear")
                                .font(.system(size: 14))
                            Text("Open Settings")
                                .font(.system(size: 14, weight: .semibold))
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 12)
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(OmiColors.purplePrimary)
                        )
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 20)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(OmiColors.backgroundSecondary.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(appState.hasScreenRecordingPermission ? Color.green.opacity(0.3) : OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
                )
        )
    }
}

// MARK: - Notification Permission Section
struct NotificationPermissionSection: View {
    @ObservedObject var appState: AppState
    @State private var isExpanded = true

    // Check if permission was explicitly denied
    private var isPermissionDenied: Bool {
        return appState.isNotificationPermissionDenied()
    }

    // Colors based on state
    private var iconBackgroundColor: Color {
        if appState.hasNotificationPermission {
            return Color.green.opacity(0.15)
        } else if isPermissionDenied {
            return Color.red.opacity(0.15)
        } else {
            return OmiColors.backgroundTertiary
        }
    }

    private var iconColor: Color {
        if appState.hasNotificationPermission {
            return .green
        } else if isPermissionDenied {
            return .red
        } else {
            return OmiColors.textSecondary
        }
    }

    private var borderColor: Color {
        if appState.hasNotificationPermission {
            return Color.green.opacity(0.3)
        } else if isPermissionDenied {
            return Color.red.opacity(0.5)
        } else {
            return OmiColors.backgroundQuaternary.opacity(0.5)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            Button(action: { withAnimation { isExpanded.toggle() } }) {
                HStack(spacing: 16) {
                    // Icon
                    ZStack {
                        Circle()
                            .fill(iconBackgroundColor)
                            .frame(width: 48, height: 48)

                        Image(systemName: isPermissionDenied ? "bell.slash.fill" : "bell.fill")
                            .font(.system(size: 22))
                            .foregroundColor(iconColor)
                    }

                    // Title and status
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 8) {
                            Text("Notifications")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(OmiColors.textPrimary)

                            notificationStatusBadge
                        }

                        Text(isPermissionDenied
                            ? "Permission was denied - enable in System Settings"
                            : "Required for proactive assistant alerts")
                            .font(.system(size: 13))
                            .foregroundColor(isPermissionDenied ? .red.opacity(0.8) : OmiColors.textTertiary)
                    }

                    Spacer()

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .padding(20)
            }
            .buttonStyle(.plain)

            // Expanded content
            if isExpanded && !appState.hasNotificationPermission {
                VStack(alignment: .leading, spacing: 16) {
                    Divider()
                        .background(OmiColors.backgroundQuaternary)

                    if isPermissionDenied {
                        // DENIED STATE - Show settings instructions
                        deniedStateContent
                    } else {
                        // NOT DETERMINED - Show normal grant flow
                        notDeterminedStateContent
                    }
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 20)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(isPermissionDenied ? Color.red.opacity(0.05) : OmiColors.backgroundSecondary.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(borderColor, lineWidth: isPermissionDenied ? 2 : 1)
                )
        )
    }

    // Status badge for notifications
    private var notificationStatusBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: appState.hasNotificationPermission ? "checkmark.circle.fill" : (isPermissionDenied ? "xmark.circle.fill" : "exclamationmark.circle.fill"))
                .font(.system(size: 12))
            Text(appState.hasNotificationPermission ? "Granted" : (isPermissionDenied ? "Denied" : "Not Granted"))
                .font(.system(size: 12, weight: .medium))
        }
        .foregroundColor(appState.hasNotificationPermission ? .green : (isPermissionDenied ? .red : OmiColors.warning))
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            Capsule()
                .fill(appState.hasNotificationPermission ? Color.green.opacity(0.15) : (isPermissionDenied ? Color.red.opacity(0.15) : OmiColors.warning.opacity(0.15)))
        )
    }

    // Content for DENIED state - shows settings instructions
    private var deniedStateContent: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Notification access was previously denied. Enable it in System Settings:")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(OmiColors.textPrimary)

            VStack(alignment: .leading, spacing: 12) {
                instructionStep(number: 1, text: "Click \"Open Settings\" below")
                instructionStep(number: 2, text: "Toggle \"Allow Notifications\" to ON")
                instructionStep(number: 3, text: "Set notification style to \"Banners\" or \"Alerts\" (not \"None\")")
            }

            Button(action: {
                appState.openNotificationPreferences()
            }) {
                HStack(spacing: 8) {
                    Image(systemName: "gear")
                        .font(.system(size: 14))
                    Text("Open Settings")
                        .font(.system(size: 14, weight: .semibold))
                }
                .foregroundColor(.white)
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(OmiColors.purplePrimary)
                )
            }
            .buttonStyle(.plain)
        }
    }

    // Content for NOT DETERMINED state - shows normal grant flow
    private var notDeterminedStateContent: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("How to grant notification access:")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(OmiColors.textPrimary)

            VStack(alignment: .leading, spacing: 12) {
                instructionStep(number: 1, text: "Click \"Grant Access\" below - a system dialog will appear")
                instructionStep(number: 2, text: "Click \"Allow\" to enable notifications")
                instructionStep(number: 3, text: "Tip: In System Settings > Notifications > Omi, set style to \"Banners\" to see visual alerts")
            }

            Button(action: {
                NSApp.activate(ignoringOtherApps: true)
                appState.requestNotificationPermission()
            }) {
                HStack(spacing: 8) {
                    Image(systemName: "hand.tap.fill")
                        .font(.system(size: 14))
                    Text("Grant Access")
                        .font(.system(size: 14, weight: .semibold))
                }
                .foregroundColor(.white)
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(OmiColors.purplePrimary)
                )
            }
            .buttonStyle(.plain)
        }
    }
}

// MARK: - Helper Views

private func statusBadge(isGranted: Bool) -> some View {
    HStack(spacing: 4) {
        Image(systemName: isGranted ? "checkmark.circle.fill" : "xmark.circle.fill")
            .font(.system(size: 12))
        Text(isGranted ? "Granted" : "Not Granted")
            .font(.system(size: 12, weight: .medium))
    }
    .foregroundColor(isGranted ? .green : OmiColors.warning)
    .padding(.horizontal, 8)
    .padding(.vertical, 4)
    .background(
        Capsule()
            .fill(isGranted ? Color.green.opacity(0.15) : OmiColors.warning.opacity(0.15))
    )
}

private func instructionStep(number: Int, text: String) -> some View {
    HStack(alignment: .top, spacing: 12) {
        Text("\(number)")
            .font(.system(size: 12, weight: .bold))
            .foregroundColor(.white)
            .frame(width: 22, height: 22)
            .background(Circle().fill(OmiColors.purplePrimary))

        Text(text)
            .font(.system(size: 13))
            .foregroundColor(OmiColors.textSecondary)
    }
}

#Preview {
    PermissionsPage(appState: AppState())
        .frame(width: 800, height: 700)
        .background(OmiColors.backgroundPrimary)
}
