@preconcurrency import AVFoundation
import AppKit
import OmiTheme
import SwiftUI

struct PermissionsPage: View {
  @ObservedObject var appState: AppState

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
        // Header
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          HStack(spacing: OmiSpacing.md) {
            Image(systemName: "exclamationmark.triangle.fill")
              .scaledFont(size: OmiType.title)
              .foregroundColor(OmiColors.warning)

            Text("Permissions Required")
              .scaledFont(size: 24, weight: .bold)
              .foregroundColor(OmiColors.textPrimary)
          }

          Text("omi needs the following permissions to work properly.")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textSecondary)
        }
        .padding(.bottom, OmiSpacing.sm)

        // Permission sections
        VStack(spacing: OmiSpacing.xl) {
          // Microphone Permission
          MicrophonePermissionSection(appState: appState)

          // Screen Recording Permission
          ScreenRecordingPermissionSection(appState: appState)

          // System Audio Permission (Core Audio process taps, macOS 14.4+)
          if #available(macOS 14.4, *) {
            SystemAudioPermissionSection(appState: appState)
          }

          // Notification Permission
          NotificationPermissionSection(appState: appState)
        }

        // All permissions granted message
        if !appState.hasMissingPermissions {
          HStack(spacing: OmiSpacing.md) {
            Image(systemName: "checkmark.circle.fill")
              .scaledFont(size: OmiType.heading)
              .foregroundColor(.green)

            Text("All permissions granted! omi is ready to use.")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)
          }
          .padding(OmiSpacing.lg)
          .frame(maxWidth: .infinity, alignment: .leading)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(Color.green.opacity(0.1))
              .overlay(
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                  .stroke(Color.green.opacity(0.3), lineWidth: 1)
              )
          )
        }

        Spacer()
      }
      .padding(OmiSpacing.xxl)
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
      Button(action: { OmiMotion.withGated { isExpanded.toggle() } }) {
        HStack(spacing: OmiSpacing.lg) {
          // Icon - pulsing animation when denied
          ZStack {
            Circle()
              .fill(iconBackgroundColor)
              .frame(width: 48, height: 48)

            Image(systemName: isPermissionDenied ? "mic.slash.fill" : "mic.fill")
              .scaledFont(size: OmiType.heading)
              .foregroundColor(iconColor)
          }

          // Title and status
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            HStack(spacing: OmiSpacing.sm) {
              Text("Microphone")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              microphoneStatusBadge
            }

            Text(
              isPermissionDenied
                ? "Permission was denied - reset required"
                : "Required for voice recording and transcription"
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(isPermissionDenied ? .red.opacity(0.8) : OmiColors.textTertiary)
          }

          Spacer()

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
        }
        .padding(OmiSpacing.xl)
      }
      .buttonStyle(.plain)

      // Expanded content - different for denied vs not determined
      if isExpanded && !appState.hasMicrophonePermission {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
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
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.bottom, OmiSpacing.xl)
      }
    }
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
        .fill(isPermissionDenied ? Color.red.opacity(0.05) : OmiColors.backgroundSecondary.opacity(0.5))
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
            .stroke(borderColor, lineWidth: isPermissionDenied ? 2 : 1)
        )
    )
  }

  // Status badge for microphone
  private var microphoneStatusBadge: some View {
    HStack(spacing: OmiSpacing.xxs) {
      Image(
        systemName: appState.hasMicrophonePermission
          ? "checkmark.circle.fill" : (isPermissionDenied ? "xmark.circle.fill" : "exclamationmark.circle.fill")
      )
      .scaledFont(size: OmiType.caption)
      Text(appState.hasMicrophonePermission ? "Granted" : (isPermissionDenied ? "Denied" : "Not Granted"))
        .scaledFont(size: OmiType.caption, weight: .medium)
    }
    .foregroundColor(appState.hasMicrophonePermission ? .green : (isPermissionDenied ? .red : OmiColors.warning))
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xxs)
    .background(
      Capsule()
        .fill(
          appState.hasMicrophonePermission
            ? Color.green.opacity(0.15)
            : (isPermissionDenied ? Color.red.opacity(0.15) : OmiColors.warning.opacity(0.15)))
    )
  }

  // Content for DENIED state - shows reset options
  // Note: Grant Access button is NOT shown here because macOS won't show the permission
  // dialog again after the user denied it. They must reset the permission first.
  private var deniedStateContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("Microphone access was previously denied. Reset the permission to try again:")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.textPrimary)

      // Option 1: Quick Reset
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        Text("Option 1: Quick Reset")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Button(action: tryDirectReset) {
          HStack(spacing: OmiSpacing.sm) {
            if isResetting {
              ProgressView()
                .scaleEffect(0.7)
                .frame(width: 14, height: 14)
            } else {
              Image(systemName: "arrow.clockwise")
                .scaledFont(size: OmiType.body)
            }
            Text(resetButtonText)
              .scaledFont(size: OmiType.body, weight: .semibold)
          }
          .foregroundColor(OmiColors.backgroundPrimary)
          .padding(.horizontal, OmiSpacing.xl)
          .padding(.vertical, OmiSpacing.sm)
          .frame(maxWidth: .infinity)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(isResetting ? Color.gray : OmiColors.accent)
          )
        }
        .buttonStyle(.plain)
        .disabled(isResetting)
      }

      // Option 2: Terminal
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        Text("Option 2: Reset via Terminal")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Button(action: tryTerminalReset) {
          HStack(spacing: OmiSpacing.sm) {
            Image(systemName: "terminal")
              .scaledFont(size: OmiType.body)
            Text("Open Terminal")
              .scaledFont(size: OmiType.body, weight: .semibold)
          }
          .foregroundColor(OmiColors.textPrimary)
          .padding(.horizontal, OmiSpacing.xl)
          .padding(.vertical, OmiSpacing.sm)
          .frame(maxWidth: .infinity)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(OmiColors.backgroundTertiary)
          )
        }
        .buttonStyle(.plain)
      }

      // Option 3: Manual
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        Text("Option 3: Manual")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        // Step 1: Open System Settings
        HStack(alignment: .top, spacing: OmiSpacing.sm) {
          Text("1.")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            Text("Open System Settings")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)

            Button(action: openSystemSettings) {
              HStack(spacing: OmiSpacing.sm) {
                Image(systemName: "gear")
                  .scaledFont(size: OmiType.body)
                Text("Open Privacy Settings")
                  .scaledFont(size: OmiType.body, weight: .semibold)
              }
              .foregroundColor(OmiColors.textPrimary)
              .padding(.horizontal, OmiSpacing.lg)
              .padding(.vertical, OmiSpacing.sm)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                  .fill(OmiColors.backgroundTertiary)
              )
            }
            .buttonStyle(.plain)
          }
        }

        // Step 2: Find Omi and toggle ON
        HStack(alignment: .top, spacing: OmiSpacing.sm) {
          Text("2.")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            Text("Find \"omi\" and toggle it ON")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)

            // Screenshot showing the toggle
            if let image = NSImage(
              contentsOfFile: Bundle.resourceBundle.path(forResource: "microphone-settings", ofType: "png") ?? "")
            {
              Image(nsImage: image)
                .resizable()
                .scaledToFit()
                .frame(maxWidth: 300)
                .cornerRadius(OmiChrome.elementRadius)
                .overlay(
                  RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
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
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("How to grant microphone access:")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.textPrimary)

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        instructionStep(number: 1, text: "Click \"Grant Access\" below - a system dialog will appear")
        instructionStep(number: 2, text: "Click \"OK\" to allow microphone access")
        instructionStep(
          number: 3,
          text:
            "If no dialog appears, find \"\(Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "omi")\" in Settings and enable it"
        )
      }

      Button(action: {
        NSApp.activate()
        appState.requestMicrophonePermission()
      }) {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "hand.tap.fill")
            .scaledFont(size: OmiType.body)
          Text("Grant Access")
            .scaledFont(size: OmiType.body, weight: .semibold)
        }
        .foregroundColor(OmiColors.backgroundPrimary)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .fill(OmiColors.accent)
        )
      }
      .buttonStyle(.plain)
    }
  }

  // MARK: - Actions

  private func tryDirectReset() {
    isResetting = true
    resetButtonText = "Resetting & Restarting..."

    // Capture the main-actor `appState` reference while still on the main
    // actor; the reset runs off-main to avoid blocking the UI during the
    // tccutil subprocess. AppState is main-actor-isolated (hence Sendable), so
    // the reference crosses the dispatch boundary safely, and
    // resetMicrophonePermissionDirect is nonisolated.
    let state = appState
    DispatchQueue.global(qos: .userInitiated).async {
      // Reset and restart the app - macOS requires restart to show permission dialog again
      let success = state.resetMicrophonePermissionDirect(shouldRestart: true)

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
      Button(action: { OmiMotion.withGated { isExpanded.toggle() } }) {
        HStack(spacing: OmiSpacing.lg) {
          // Icon
          ZStack {
            Circle()
              .fill(
                appState.isScreenRecordingStale
                  ? Color.red.opacity(0.15)
                  : (appState.hasScreenRecordingPermission ? Color.green.opacity(0.15) : OmiColors.backgroundTertiary)
              )
              .frame(width: 48, height: 48)

            Image(
              systemName: appState.isScreenRecordingStale
                ? "rectangle.on.rectangle.slash" : "rectangle.inset.filled.and.person.filled"
            )
            .scaledFont(size: OmiType.heading)
            .foregroundColor(
              appState.isScreenRecordingStale
                ? .red : (appState.hasScreenRecordingPermission ? .green : OmiColors.textSecondary))
          }

          // Title and status
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            HStack(spacing: OmiSpacing.sm) {
              Text("Screen Recording")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              if appState.isScreenRecordingStale {
                HStack(spacing: OmiSpacing.xxs) {
                  Image(systemName: "exclamationmark.triangle.fill")
                    .scaledFont(size: OmiType.caption)
                  Text("Re-enable Required")
                    .scaledFont(size: OmiType.caption, weight: .medium)
                }
                .foregroundColor(.red)
                .padding(.horizontal, OmiSpacing.sm)
                .padding(.vertical, OmiSpacing.xxs)
                .background(
                  Capsule()
                    .fill(Color.red.opacity(0.15))
                )
              } else {
                statusBadge(isGranted: appState.hasScreenRecordingPermission)
              }
            }

            Text(
              appState.isScreenRecordingStale
                ? "Permission needs re-enabling after app update"
                : "Required for proactive monitoring and context awareness"
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(appState.isScreenRecordingStale ? .red.opacity(0.8) : OmiColors.textTertiary)
          }

          Spacer()

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
        }
        .padding(OmiSpacing.xl)
      }
      .buttonStyle(.plain)

      // Expanded content
      if isExpanded && (!appState.hasScreenRecordingPermission || appState.isScreenRecordingStale) {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          Divider()
            .background(OmiColors.backgroundQuaternary)

          if appState.isScreenRecordingStale {
            // STALE STATE - developer signing changed, user must toggle off/on
            stalePermissionContent
          } else {
            // NORMAL STATE - first-time grant flow
            normalGrantContent
          }
        }
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.bottom, OmiSpacing.xl)
      }
    }
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
        .fill(appState.isScreenRecordingStale ? Color.red.opacity(0.05) : OmiColors.backgroundSecondary.opacity(0.5))
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
            .stroke(
              appState.hasScreenRecordingPermission
                ? Color.green.opacity(0.3)
                : (appState.isScreenRecordingStale
                  ? Color.red.opacity(0.5) : OmiColors.backgroundQuaternary.opacity(0.5)),
              lineWidth: appState.isScreenRecordingStale ? 2 : 1)
        )
    )
  }

  // Content for STALE state - developer signing changed, user must remove and re-add
  private var stalePermissionContent: some View {
    let appName = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "omi"
    return VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("Screen recording needs to be re-enabled after an app update.")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.textPrimary)

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        // Step 1 — Open Settings button inline
        HStack(alignment: .top, spacing: OmiSpacing.md) {
          Text("1")
            .scaledFont(size: OmiType.caption, weight: .bold)
            .foregroundColor(OmiColors.backgroundPrimary)
            .frame(width: 22, height: 22)
            .background(Circle().fill(OmiColors.accent))

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            Text("Open Screen Recording settings")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)

            Button(action: {
              ScreenCaptureService.openScreenRecordingPreferences()
            }) {
              HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "gear")
                  .scaledFont(size: OmiType.caption)
                Text("Open Settings")
                  .scaledFont(size: OmiType.caption, weight: .semibold)
              }
              .foregroundColor(OmiColors.backgroundPrimary)
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.xs)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                  .fill(OmiColors.accent)
              )
            }
            .buttonStyle(.plain)
          }
        }

        instructionStep(number: 2, text: "Find \"\(appName)\" in the Screen Recording list")
        instructionStep(number: 3, text: "Click on \"\(appName)\", then click the minus (−) button to remove it")

        // Step 4 — Grant button inline
        HStack(alignment: .top, spacing: OmiSpacing.md) {
          Text("4")
            .scaledFont(size: OmiType.caption, weight: .bold)
            .foregroundColor(OmiColors.backgroundPrimary)
            .frame(width: 22, height: 22)
            .background(Circle().fill(OmiColors.accent))

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            Text("Come back to omi and grant the permission")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)

            Button(action: {
              // Reset stale state so Grant flow works fresh
              appState.isScreenRecordingStale = false
              appState.screenRecordingGrantAttempts = 0
              ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
            }) {
              HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "checkmark.shield")
                  .scaledFont(size: OmiType.caption)
                Text("Grant")
                  .scaledFont(size: OmiType.caption, weight: .semibold)
              }
              .foregroundColor(.white)
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.xs)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                  .fill(Color.green)
              )
            }
            .buttonStyle(.plain)
          }
        }
      }
    }
  }

  // Content for NORMAL state - first-time grant flow
  private var normalGrantContent: some View {
    let appName = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "omi"
    return VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("How to grant screen recording access:")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.textPrimary)

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        instructionStep(number: 1, text: "Click \"Open Settings\" below - this will make omi appear in the list")
        instructionStep(number: 2, text: "Find \"\(appName)\" in the Screen Recording list")
        instructionStep(number: 3, text: "Toggle the switch to enable screen recording")
        instructionStep(number: 4, text: "Return to omi - permission will update automatically")
      }

      // Tutorial GIF
      AnimatedGIFView(gifName: "permissions")
        .frame(maxWidth: 400, maxHeight: 300)
        .cornerRadius(OmiChrome.smallControlRadius)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .stroke(OmiColors.backgroundQuaternary, lineWidth: 1)
        )

      Button(action: {
        ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
        // Track attempt — if still not granted on next check, show recovery instructions
        appState.screenRecordingGrantAttempts += 1
      }) {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "gear")
            .scaledFont(size: OmiType.body)
          Text("Open Settings")
            .scaledFont(size: OmiType.body, weight: .semibold)
        }
        .foregroundColor(OmiColors.backgroundPrimary)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .fill(OmiColors.accent)
        )
      }
      .buttonStyle(.plain)
    }
  }
}

// MARK: - System Audio Permission Section
struct SystemAudioPermissionSection: View {
  @ObservedObject var appState: AppState
  @State private var isExpanded = true
  @State private var isTesting = false

  private var status: SystemAudioPermissionStatus {
    appState.systemAudioPermissionStatus
  }

  private var mode: AssistantSettings.SystemAudioCaptureMode {
    appState.effectiveSystemAudioMode
  }

  private var isDisabledBySetting: Bool {
    mode == .never
  }

  private var isGranted: Bool {
    status == .granted
  }

  private var iconBackgroundColor: Color {
    switch status {
    case .granted:
      return Color.green.opacity(0.15)
    case .denied:
      return OmiColors.warning.opacity(0.15)
    case .unsupported:
      return OmiColors.backgroundTertiary.opacity(0.7)
    case .unknown:
      return OmiColors.backgroundTertiary
    }
  }

  private var iconColor: Color {
    switch status {
    case .granted:
      return .green
    case .denied:
      return OmiColors.warning
    case .unsupported:
      return OmiColors.textTertiary
    case .unknown:
      return OmiColors.textSecondary
    }
  }

  private var borderColor: Color {
    switch status {
    case .granted:
      return Color.green.opacity(0.3)
    case .denied:
      return OmiColors.warning.opacity(0.5)
    case .unsupported, .unknown:
      return OmiColors.backgroundQuaternary.opacity(0.5)
    }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Button(action: { OmiMotion.withGated { isExpanded.toggle() } }) {
        HStack(spacing: OmiSpacing.lg) {
          ZStack {
            Circle()
              .fill(iconBackgroundColor)
              .frame(width: 48, height: 48)

            Image(systemName: isGranted ? "speaker.wave.2.fill" : "speaker.slash.fill")
              .scaledFont(size: OmiType.heading)
              .foregroundColor(iconColor)
          }

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            HStack(spacing: OmiSpacing.sm) {
              Text("System Audio")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              systemAudioStatusBadge
            }

            Text(descriptionText)
              .scaledFont(size: OmiType.body)
              .foregroundColor(status == .denied ? OmiColors.warning : OmiColors.textTertiary)
          }

          Spacer()

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
        }
        .padding(OmiSpacing.xl)
      }
      .buttonStyle(.plain)

      if isExpanded {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          Divider()
            .background(OmiColors.backgroundQuaternary)

          expandedContent
        }
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.bottom, OmiSpacing.xl)
      }
    }
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
        .fill(OmiColors.backgroundSecondary.opacity(0.5))
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
            .stroke(borderColor, lineWidth: status == .denied ? 2 : 1)
        )
    )
  }

  private var descriptionText: String {
    if isDisabledBySetting {
      return "Disabled in Settings > General"
    }

    switch status {
    case .granted:
      return "Captures audio from calls, videos, and other apps"
    case .denied:
      return "Access was not granted or the last system audio test failed"
    case .unsupported:
      return "Requires macOS 14.4 or later"
    case .unknown:
      return "Test access to confirm Omi can capture audio from other apps"
    }
  }

  private var systemAudioStatusBadge: some View {
    let label: String
    let foreground: Color
    let background: Color
    let icon: String

    if isDisabledBySetting {
      label = "Disabled"
      foreground = OmiColors.textTertiary
      background = OmiColors.backgroundTertiary.opacity(0.8)
      icon = "minus.circle.fill"
    } else {
      switch status {
      case .granted:
        label = "Granted"
        foreground = .green
        background = Color.green.opacity(0.15)
        icon = "checkmark.circle.fill"
      case .denied:
        label = "Not Granted"
        foreground = OmiColors.warning
        background = OmiColors.warning.opacity(0.15)
        icon = "xmark.circle.fill"
      case .unsupported:
        label = "Unsupported"
        foreground = OmiColors.textTertiary
        background = OmiColors.backgroundTertiary.opacity(0.8)
        icon = "slash.circle.fill"
      case .unknown:
        label = "Unknown"
        foreground = OmiColors.textSecondary
        background = OmiColors.backgroundTertiary.opacity(0.8)
        icon = "questionmark.circle.fill"
      }
    }

    return HStack(spacing: OmiSpacing.xxs) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.caption)
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
    }
    .foregroundColor(foreground)
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xxs)
    .background(Capsule().fill(background))
  }

  private var expandedContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      if isDisabledBySetting {
        Text("System audio capture is set to Never in Settings > General. Change that setting before testing access.")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
      } else if status == .unsupported {
        Text("System audio capture requires macOS 14.4 or later.")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
      } else if status == .granted {
        Text("System audio access was confirmed by a successful Core Audio tap.")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
      } else {
        Text("How to grant system audio access:")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)

        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          neutralInstructionStep(number: 1, text: "Click Test Access below")
          neutralInstructionStep(
            number: 2, text: "If System Settings opens, enable Omi under Screen & System Audio Recording")
          neutralInstructionStep(number: 3, text: "Return to Omi and click Test Access again")
        }
      }

      Button(action: testSystemAudioAccess) {
        HStack(spacing: OmiSpacing.sm) {
          if isTesting {
            ProgressView()
              .scaleEffect(0.7)
          } else {
            Image(systemName: "speaker.wave.2.fill")
              .scaledFont(size: OmiType.body)
          }
          Text(isGranted ? "Test Again" : "Test Access")
            .scaledFont(size: OmiType.body, weight: .semibold)
        }
        .foregroundColor(OmiColors.textPrimary)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .fill(OmiColors.backgroundTertiary)
            .overlay(
              RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .stroke(OmiColors.backgroundQuaternary, lineWidth: 1)
            )
        )
      }
      .buttonStyle(.plain)
      .disabled(isTesting || isDisabledBySetting || status == .unsupported)
      .opacity((isTesting || isDisabledBySetting || status == .unsupported) ? 0.6 : 1)
    }
  }

  private func testSystemAudioAccess() {
    isTesting = true
    appState.triggerSystemAudioPermission()
    DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
      isTesting = false
    }
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
      Button(action: { OmiMotion.withGated { isExpanded.toggle() } }) {
        HStack(spacing: OmiSpacing.lg) {
          // Icon
          ZStack {
            Circle()
              .fill(iconBackgroundColor)
              .frame(width: 48, height: 48)

            Image(systemName: isPermissionDenied ? "bell.slash.fill" : "bell.fill")
              .scaledFont(size: OmiType.heading)
              .foregroundColor(iconColor)
          }

          // Title and status
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            HStack(spacing: OmiSpacing.sm) {
              Text("Notifications")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              notificationStatusBadge
            }

            Text(
              isPermissionDenied
                ? "Permission was denied - enable in System Settings"
                : "Required for proactive assistant alerts"
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(isPermissionDenied ? .red.opacity(0.8) : OmiColors.textTertiary)
          }

          Spacer()

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
        }
        .padding(OmiSpacing.xl)
      }
      .buttonStyle(.plain)

      // Expanded content
      if isExpanded && !appState.hasNotificationPermission {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
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
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.bottom, OmiSpacing.xl)
      }
    }
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
        .fill(isPermissionDenied ? Color.red.opacity(0.05) : OmiColors.backgroundSecondary.opacity(0.5))
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
            .stroke(borderColor, lineWidth: isPermissionDenied ? 2 : 1)
        )
    )
  }

  // Status badge for notifications
  private var notificationStatusBadge: some View {
    HStack(spacing: OmiSpacing.xxs) {
      Image(
        systemName: appState.hasNotificationPermission
          ? "checkmark.circle.fill" : (isPermissionDenied ? "xmark.circle.fill" : "exclamationmark.circle.fill")
      )
      .scaledFont(size: OmiType.caption)
      Text(appState.hasNotificationPermission ? "Granted" : (isPermissionDenied ? "Denied" : "Not Granted"))
        .scaledFont(size: OmiType.caption, weight: .medium)
    }
    .foregroundColor(appState.hasNotificationPermission ? .green : (isPermissionDenied ? .red : OmiColors.warning))
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xxs)
    .background(
      Capsule()
        .fill(
          appState.hasNotificationPermission
            ? Color.green.opacity(0.15)
            : (isPermissionDenied ? Color.red.opacity(0.15) : OmiColors.warning.opacity(0.15)))
    )
  }

  // Content for DENIED state - shows settings instructions
  private var deniedStateContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("Notification access was previously denied. Enable it in System Settings:")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.textPrimary)

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        instructionStep(number: 1, text: "Click \"Open Settings\" below")
        instructionStep(number: 2, text: "Toggle \"Allow Notifications\" to ON")
        instructionStep(number: 3, text: "Set notification style to \"Banners\" or \"Alerts\" (not \"None\")")
      }

      Button(action: {
        appState.openNotificationPreferences()
      }) {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "gear")
            .scaledFont(size: OmiType.body)
          Text("Open Settings")
            .scaledFont(size: OmiType.body, weight: .semibold)
        }
        .foregroundColor(OmiColors.backgroundPrimary)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .fill(OmiColors.accent)
        )
      }
      .buttonStyle(.plain)
    }
  }

  // Content for NOT DETERMINED state - shows normal grant flow
  private var notDeterminedStateContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("How to grant notification access:")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.textPrimary)

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        instructionStep(number: 1, text: "Click \"Grant Access\" below - a system dialog will appear")
        instructionStep(number: 2, text: "Click \"Allow\" to enable notifications")
        instructionStep(
          number: 3,
          text: "Tip: In System Settings > Notifications > omi, set style to \"Banners\" to see visual alerts")
      }

      Button(action: {
        NSApp.activate()
        appState.requestNotificationPermission()
      }) {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "hand.tap.fill")
            .scaledFont(size: OmiType.body)
          Text("Grant Access")
            .scaledFont(size: OmiType.body, weight: .semibold)
        }
        .foregroundColor(OmiColors.backgroundPrimary)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .fill(OmiColors.accent)
        )
      }
      .buttonStyle(.plain)
    }
  }
}

// MARK: - Helper Views

@MainActor private func statusBadge(isGranted: Bool) -> some View {
  HStack(spacing: OmiSpacing.xxs) {
    Image(systemName: isGranted ? "checkmark.circle.fill" : "xmark.circle.fill")
      .scaledFont(size: OmiType.caption)
    Text(isGranted ? "Granted" : "Not Granted")
      .scaledFont(size: OmiType.caption, weight: .medium)
  }
  .foregroundColor(isGranted ? .green : OmiColors.warning)
  .padding(.horizontal, OmiSpacing.sm)
  .padding(.vertical, OmiSpacing.xxs)
  .background(
    Capsule()
      .fill(isGranted ? Color.green.opacity(0.15) : OmiColors.warning.opacity(0.15))
  )
}

/// Numbered how-to row. Neutral styling by default — purple is off-brand
/// (repo UI rule: never use purple anywhere).
@MainActor private func instructionStep(
  number: Int, text: String,
  numberColor: Color = OmiColors.textPrimary,
  circleFill: Color = OmiColors.backgroundTertiary
) -> some View {
  HStack(alignment: .top, spacing: OmiSpacing.md) {
    Text("\(number)")
      .scaledFont(size: OmiType.caption, weight: .bold)
      .foregroundColor(numberColor)
      .frame(width: 22, height: 22)
      .background(Circle().fill(circleFill))

    Text(text)
      .scaledFont(size: OmiType.body)
      .foregroundColor(OmiColors.textSecondary)
  }
}

/// Kept as an alias for the System Audio section (now identical to the default).
@MainActor private func neutralInstructionStep(number: Int, text: String) -> some View {
  instructionStep(number: number, text: text)
}

#if canImport(PreviewsMacros)
  #Preview {
    PermissionsPage(appState: AppState())
      .frame(width: 800, height: 700)
      .background(OmiColors.backgroundPrimary)
  }
#endif
