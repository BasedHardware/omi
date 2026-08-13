@preconcurrency import AVFoundation
import AppKit
import OmiTheme
import SwiftUI

struct PermissionsPage: View {
  @ObservedObject var appState: AppState

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
        // The page's own heading. `stepHeadline` rather than a hand-assembled size and weight: the
        // role carries its tracking too, and a headline set without it is a different product.
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          HStack(spacing: OmiSpacing.md) {
            Image(systemName: "exclamationmark.triangle.fill")
              .font(.system(size: 22, weight: .semibold))
              .foregroundColor(SettingsInk.notice)

            Text("Permissions Required")
              .inkStyle(.stepHeadline, color: Ink.primary)
          }

          Text("omi needs the following permissions to work properly.")
            .inkStyle(.prose, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
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
              .foregroundColor(Ink.listeningGreen)

            Text("All permissions granted! omi is ready to use.")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(Ink.primary)
          }
          .padding(OmiSpacing.lg)
          .frame(maxWidth: .infinity, alignment: .leading)
          .background(
            RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
              .fill(Ink.listeningGreen.opacity(0.1))
              .overlay(
                RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
                  .stroke(Ink.listeningGreen.opacity(0.3), lineWidth: 1)
              )
          )
        }

        Spacer()
      }
      .padding(.horizontal, SettingsGlassMetrics.paneHorizontalPadding)
      .padding(.top, SettingsGlassMetrics.paneTopPadding)
      .padding(.bottom, SettingsGlassMetrics.paneBottomPadding)
      // The list column, not the reading column: a permission row is a sentence with a state word
      // after it, so it takes the width `InkLayout.contentMaxWidth` deliberately does not.
      .frame(maxWidth: InkLayout.permissionsMaxWidth, alignment: .leading)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    // No background: the window wears the glass, and the glass owns the ground.
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
      return Ink.listeningGreen.opacity(0.15)
    } else if isPermissionDenied {
      return Ink.errorRed.opacity(0.15)
    } else {
      return Ink.rowFill
    }
  }

  private var iconColor: Color {
    if appState.hasMicrophonePermission {
      return Ink.listeningGreen
    } else if isPermissionDenied {
      return Ink.errorRed
    } else {
      return Ink.secondary
    }
  }

  private var borderColor: Color {
    if appState.hasMicrophonePermission {
      return Ink.listeningGreen.opacity(0.3)
    } else if isPermissionDenied {
      return Ink.errorRed.opacity(0.5)
    } else {
      return Ink.hairline
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
                .foregroundColor(Ink.primary)

              microphoneStatusBadge
            }

            Text(
              isPermissionDenied
                ? "Permission was denied - reset required"
                : "Required for voice recording and transcription"
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(isPermissionDenied ? Ink.errorRed : Ink.secondary)
          }

          Spacer()

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.secondary)
        }
        .padding(OmiSpacing.xl)
      }
      .buttonStyle(.plain)

      // Expanded content - different for denied vs not determined
      if isExpanded && !appState.hasMicrophonePermission {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          GlassSeparator()

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
      RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
        .fill(isPermissionDenied ? Ink.errorRed.opacity(0.05) : Ink.wash)
        .overlay(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .stroke(borderColor, lineWidth: 1)
        )
    )
  }

  // Status badge for microphone
  private var microphoneStatusBadge: some View {
    permissionChip(granted: appState.hasMicrophonePermission, denied: isPermissionDenied)
  }

  // Content for DENIED state - shows reset options
  // Note: Grant Access button is NOT shown here because macOS won't show the permission
  // dialog again after the user denied it. They must reset the permission first.
  private var deniedStateContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("Microphone access was previously denied. Reset the permission to try again:")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.primary)

      // Option 1: Quick Reset
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        Text("Option 1: Quick Reset")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)

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
          .foregroundColor(Ink.surface)
          .padding(.horizontal, OmiSpacing.xl)
          .padding(.vertical, OmiSpacing.sm)
          .frame(maxWidth: .infinity)
          .background(
            RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
              .fill(isResetting ? Ink.secondary : Ink.accent)
          )
        }
        .buttonStyle(.plain)
        .disabled(isResetting)
      }

      // Option 2: Terminal
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        Text("Option 2: Reset via Terminal")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)

        Button(action: tryTerminalReset) {
          HStack(spacing: OmiSpacing.sm) {
            Image(systemName: "terminal")
              .scaledFont(size: OmiType.body)
            Text("Open Terminal")
              .scaledFont(size: OmiType.body, weight: .semibold)
          }
          .foregroundColor(Ink.primary)
          .padding(.horizontal, OmiSpacing.xl)
          .padding(.vertical, OmiSpacing.sm)
          .frame(maxWidth: .infinity)
          .background(
            RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
              .fill(Ink.rowFill)
          )
        }
        .buttonStyle(.plain)
      }

      // Option 3: Manual
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        Text("Option 3: Manual")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)

        // Step 1: Open System Settings
        HStack(alignment: .top, spacing: OmiSpacing.sm) {
          Text("1.")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.secondary)

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            Text("Open System Settings")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)

            Button(action: openSystemSettings) {
              HStack(spacing: OmiSpacing.sm) {
                Image(systemName: "gear")
                  .scaledFont(size: OmiType.body)
                Text("Open Privacy Settings")
                  .scaledFont(size: OmiType.body, weight: .semibold)
              }
              .foregroundColor(Ink.primary)
              .padding(.horizontal, OmiSpacing.lg)
              .padding(.vertical, OmiSpacing.sm)
              .background(
                RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
                  .fill(Ink.rowFill)
              )
            }
            .buttonStyle(.plain)
          }
        }

        // Step 2: Find Omi and toggle ON
        HStack(alignment: .top, spacing: OmiSpacing.sm) {
          Text("2.")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.secondary)

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            Text("Find \"omi\" and toggle it ON")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)

            // Screenshot showing the toggle
            if let image = NSImage(
              contentsOfFile: Bundle.resourceBundle.path(forResource: "microphone-settings", ofType: "png") ?? "")
            {
              Image(nsImage: image)
                .resizable()
                .scaledToFit()
                .frame(maxWidth: 300)
                .cornerRadius(SettingsGlassMetrics.controlRadius)
                .overlay(
                  RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
                    .stroke(Ink.hairline, lineWidth: 1)
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
        .foregroundColor(Ink.primary)

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
        .foregroundColor(Ink.surface)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .fill(Ink.primary)
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
                  ? Ink.errorRed.opacity(0.15)
                  : (appState.hasScreenRecordingPermission ? Ink.listeningGreen.opacity(0.15) : Ink.rowFill)
              )
              .frame(width: 48, height: 48)

            Image(
              systemName: appState.isScreenRecordingStale
                ? "rectangle.on.rectangle.slash" : "rectangle.inset.filled.and.person.filled"
            )
            .scaledFont(size: OmiType.heading)
            .foregroundColor(
              appState.isScreenRecordingStale
                ? Ink.errorRed : (appState.hasScreenRecordingPermission ? Ink.listeningGreen : Ink.secondary))
          }

          // Title and status
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            HStack(spacing: OmiSpacing.sm) {
              Text("Screen Recording")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(Ink.primary)

              if appState.isScreenRecordingStale {
                SettingsStatusChip(text: "Re-enable Required", tint: Ink.errorRed)
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
            .foregroundColor(appState.isScreenRecordingStale ? Ink.errorRed : Ink.secondary)
          }

          Spacer()

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.secondary)
        }
        .padding(OmiSpacing.xl)
      }
      .buttonStyle(.plain)

      // Expanded content
      if isExpanded && (!appState.hasScreenRecordingPermission || appState.isScreenRecordingStale) {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          GlassSeparator()

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
      RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
        .fill(appState.isScreenRecordingStale ? Ink.errorRed.opacity(0.05) : Ink.wash)
        .overlay(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .stroke(
              appState.hasScreenRecordingPermission
                ? Ink.listeningGreen.opacity(0.3)
                : (appState.isScreenRecordingStale
                  ? Ink.errorRed.opacity(0.5) : Ink.hairline),
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
        .foregroundColor(Ink.primary)

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        // Step 1 — Open Settings button inline
        HStack(alignment: .top, spacing: OmiSpacing.md) {
          Text("1")
            .scaledFont(size: OmiType.caption, weight: .bold)
            .foregroundColor(Ink.surface)
            .frame(width: 22, height: 22)
            .background(Circle().fill(Ink.primary))

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            Text("Open Screen Recording settings")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)

            Button(action: {
              ScreenCaptureService.openScreenRecordingPreferences()
            }) {
              HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "gear")
                  .scaledFont(size: OmiType.caption)
                Text("Open Settings")
                  .scaledFont(size: OmiType.caption, weight: .semibold)
              }
              .foregroundColor(Ink.surface)
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.xs)
              .background(
                RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
                  .fill(Ink.primary)
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
            .foregroundColor(Ink.surface)
            .frame(width: 22, height: 22)
            .background(Circle().fill(Ink.primary))

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            Text("Come back to omi and grant the permission")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)

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
              // The same fill as step 1's button above it, and not `Ink.listeningGreen`: the
              // inverted label is only legible over `Ink.primary` — `Ink.surface` on `systemGreen`
              // measures about 2:1 in the light appearance. Green is the *granted* readout on this
              // page, not the colour of the button that asks; the shield glyph carries that.
              .foregroundColor(Ink.surface)
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.xs)
              .background(
                RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
                  .fill(Ink.primary)
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
        .foregroundColor(Ink.primary)

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        instructionStep(number: 1, text: "Click \"Open Settings\" below - this will make omi appear in the list")
        instructionStep(number: 2, text: "Find \"\(appName)\" in the Screen Recording list")
        instructionStep(number: 3, text: "Toggle the switch to enable screen recording")
        instructionStep(number: 4, text: "Return to omi - permission will update automatically")
      }

      // Tutorial GIF
      AnimatedGIFView(gifName: "permissions")
        .frame(maxWidth: 400, maxHeight: 300)
        .cornerRadius(SettingsGlassMetrics.cardRadius)
        .overlay(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .stroke(Ink.hairline, lineWidth: 1)
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
        .foregroundColor(Ink.surface)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .fill(Ink.primary)
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

  private var isGranted: Bool {
    status == .granted
  }

  private var iconBackgroundColor: Color {
    switch status {
    case .granted:
      return Ink.listeningGreen.opacity(0.15)
    case .denied:
      return SettingsInk.notice.opacity(0.15)
    case .unsupported:
      return Ink.rowFill
    case .unknown:
      return Ink.rowFill
    }
  }

  private var iconColor: Color {
    switch status {
    case .granted:
      return Ink.listeningGreen
    case .denied:
      return SettingsInk.notice
    case .unsupported:
      return Ink.secondary
    case .unknown:
      return Ink.secondary
    }
  }

  private var borderColor: Color {
    switch status {
    case .granted:
      return Ink.listeningGreen.opacity(0.3)
    case .denied:
      return SettingsInk.notice.opacity(0.5)
    case .unsupported, .unknown:
      return Ink.hairline
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
                .foregroundColor(Ink.primary)

              systemAudioStatusBadge
            }

            Text(descriptionText)
              .scaledFont(size: OmiType.body)
              .foregroundColor(status == .denied ? SettingsInk.notice : Ink.secondary)
          }

          Spacer()

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.secondary)
        }
        .padding(OmiSpacing.xl)
      }
      .buttonStyle(.plain)

      if isExpanded {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          GlassSeparator()

          expandedContent
        }
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.bottom, OmiSpacing.xl)
      }
    }
    .background(
      RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
        .fill(Ink.wash)
        .overlay(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .stroke(borderColor, lineWidth: status == .denied ? 2 : 1)
        )
    )
  }

  private var descriptionText: String {
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
    switch status {
    case .granted: return SettingsStatusChip(text: "Granted", tint: Ink.listeningGreen)
    case .denied: return SettingsStatusChip(text: "Not Granted", tint: SettingsInk.notice)
    case .unsupported: return SettingsStatusChip(text: "Unsupported", tint: Ink.secondary)
    case .unknown: return SettingsStatusChip(text: "Unknown", tint: Ink.secondary)
    }
  }

  private var expandedContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      if status == .unsupported {
        Text("System audio capture requires macOS 14.4 or later.")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
      } else if status == .granted {
        Text("System audio access was confirmed by a successful Core Audio tap.")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
      } else {
        Text("How to grant system audio access:")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)

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
        .foregroundColor(Ink.primary)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .fill(Ink.rowFill)
            .overlay(
              RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
                .stroke(Ink.hairline, lineWidth: 1)
            )
        )
      }
      .buttonStyle(.plain)
      .disabled(isTesting || status == .unsupported)
      .opacity((isTesting || status == .unsupported) ? 0.6 : 1)
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
      return Ink.listeningGreen.opacity(0.15)
    } else if isPermissionDenied {
      return Ink.errorRed.opacity(0.15)
    } else {
      return Ink.rowFill
    }
  }

  private var iconColor: Color {
    if appState.hasNotificationPermission {
      return Ink.listeningGreen
    } else if isPermissionDenied {
      return Ink.errorRed
    } else {
      return Ink.secondary
    }
  }

  private var borderColor: Color {
    if appState.hasNotificationPermission {
      return Ink.listeningGreen.opacity(0.3)
    } else if isPermissionDenied {
      return Ink.errorRed.opacity(0.5)
    } else {
      return Ink.hairline
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
                .foregroundColor(Ink.primary)

              notificationStatusBadge
            }

            Text(
              isPermissionDenied
                ? "Permission was denied - enable in System Settings"
                : "Required for proactive assistant alerts"
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(isPermissionDenied ? Ink.errorRed : Ink.secondary)
          }

          Spacer()

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.secondary)
        }
        .padding(OmiSpacing.xl)
      }
      .buttonStyle(.plain)

      // Expanded content
      if isExpanded && !appState.hasNotificationPermission {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          GlassSeparator()

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
      RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
        .fill(isPermissionDenied ? Ink.errorRed.opacity(0.05) : Ink.wash)
        .overlay(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .stroke(borderColor, lineWidth: 1)
        )
    )
  }

  // Status badge for notifications
  private var notificationStatusBadge: some View {
    permissionChip(granted: appState.hasNotificationPermission, denied: isPermissionDenied)
  }

  // Content for DENIED state - shows settings instructions
  private var deniedStateContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("Notification access was previously denied. Enable it in System Settings:")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.primary)

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
        .foregroundColor(Ink.surface)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .fill(Ink.primary)
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
        .foregroundColor(Ink.primary)

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
        .foregroundColor(Ink.surface)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .fill(Ink.primary)
        )
      }
      .buttonStyle(.plain)
    }
  }
}

// MARK: - Helper Views

/// The state word beside a permission's name.
///
/// `SettingsStatusChip` composes its ground from the tint rather than taking a second colour, so the
/// fill and the label here cannot drift into a contrast pair nobody keeps true. Not granted is
/// `SettingsInk.notice` and not `Ink.errorRed`: an unanswered permission is a thing to do, not a
/// thing that failed.
@MainActor private func statusBadge(isGranted: Bool) -> some View {
  SettingsStatusChip(
    text: isGranted ? "Granted" : "Not Granted",
    tint: isGranted ? Ink.listeningGreen : SettingsInk.notice)
}

/// The three-state version, for the capabilities macOS lets the user *refuse* rather than merely
/// leave unanswered.
///
/// Microphone and Notifications each carried their own hand-rolled capsule — an icon, a tint, a
/// 15% wash, spelled out twice and differing from the two rows beside them, which already used
/// `SettingsStatusChip`. Four permission rows on one page had three badge designs between them.
/// Refused is `Ink.errorRed` and merely unanswered is `SettingsInk.notice`, for the reason
/// `statusBadge` gives: a permission nobody has answered yet is a thing to do, not a thing that
/// failed.
@MainActor private func permissionChip(granted: Bool, denied: Bool) -> some View {
  if granted {
    return SettingsStatusChip(text: "Granted", tint: Ink.listeningGreen)
  }
  return denied
    ? SettingsStatusChip(text: "Denied", tint: Ink.errorRed)
    : SettingsStatusChip(text: "Not Granted", tint: SettingsInk.notice)
}

/// Numbered how-to row. Neutral by default: the disc is `Ink.rowFill` and the numeral
/// `Ink.primary`, so the step index reads without spending the one accent on it (INV-UI-1).
@MainActor private func instructionStep(
  number: Int, text: String,
  numberColor: Color = Ink.primary,
  circleFill: Color = Ink.rowFill
) -> some View {
  HStack(alignment: .top, spacing: OmiSpacing.md) {
    Text("\(number)")
      .scaledFont(size: OmiType.caption, weight: .bold)
      .foregroundColor(numberColor)
      .frame(width: 22, height: 22)
      .background(Circle().fill(circleFill))

    Text(text)
      .scaledFont(size: OmiType.body)
      .foregroundColor(Ink.secondary)
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
      .background(Color.clear)
  }
#endif
