@preconcurrency import AVFoundation
import AppKit
import OmiTheme
import SwiftUI

struct PermissionsPage: View {
  @ObservedObject var appState: AppState

  private var allRequiredGranted: Bool { !appState.hasMissingPermissions }

  private var microphoneNeedsAction: Bool {
    PermissionsPageChrome.microphoneNeedsAction(granted: appState.hasMicrophonePermission)
  }

  private var screenRecordingNeedsAction: Bool {
    PermissionsPageChrome.screenRecordingNeedsAction(
      granted: appState.hasScreenRecordingPermission,
      stale: appState.isScreenRecordingStale)
  }

  private var notificationsNeedAction: Bool {
    PermissionsPageChrome.notificationsNeedAction(granted: appState.hasNotificationPermission)
  }

  private var systemAudioNeedsAction: Bool {
    guard showsSystemAudio else { return false }
    return PermissionsPageChrome.systemAudioNeedsAction(
      status: appState.systemAudioPermissionStatus)
  }

  private var accessibilityNeedsAction: Bool {
    PermissionsPageChrome.accessibilityNeedsAction(
      granted: appState.hasAccessibilityPermission,
      broken: appState.isAccessibilityBroken)
  }

  private var bluetoothNeedsAction: Bool {
    guard showsBluetooth else { return false }
    return PermissionsPageChrome.bluetoothNeedsAction(granted: appState.hasBluetoothPermission)
  }

  /// Bluetooth is only probed once the radio has been initialised, which happens when the user
  /// actually has an Omi device in play. Reporting "Not Granted" for a permission that was never
  /// asked about would be a claim the app cannot support — and a nag aimed at people who own no
  /// wearable. A proven grant still shows, so a later revocation is visible.
  private var showsBluetooth: Bool {
    appState.hasBluetoothPermission || appState.bluetoothStateCancellable != nil
  }

  private var fullDiskAccessNeedsAction: Bool {
    PermissionsPageChrome.fullDiskAccessNeedsAction(granted: appState.hasFullDiskAccess)
  }

  private var automationNeedsAction: Bool {
    PermissionsPageChrome.automationNeedsAction(granted: appState.hasAutomationPermission)
  }

  private var showsSystemAudio: Bool {
    if #available(macOS 14.4, *) { return true }
    return false
  }

  private var hasActionablePermissions: Bool {
    microphoneNeedsAction || screenRecordingNeedsAction || systemAudioNeedsAction || notificationsNeedAction
      || accessibilityNeedsAction
  }

  private var hasSupportingActions: Bool {
    bluetoothNeedsAction || fullDiskAccessNeedsAction || automationNeedsAction
  }

  private var hasGrantedPermissions: Bool {
    !microphoneNeedsAction || !screenRecordingNeedsAction || (showsSystemAudio && !systemAudioNeedsAction)
      || !notificationsNeedAction || !accessibilityNeedsAction
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
        header
          .padding(.bottom, OmiSpacing.sm)

        if allRequiredGranted {
          allGrantedBanner
        }

        if hasActionablePermissions {
          VStack(spacing: OmiSpacing.xl) {
            if microphoneNeedsAction {
              MicrophonePermissionSection(appState: appState)
            }
            if screenRecordingNeedsAction {
              ScreenRecordingPermissionSection(appState: appState)
            }
            if showsSystemAudio, systemAudioNeedsAction {
              SystemAudioPermissionSection(appState: appState)
            }
            if notificationsNeedAction {
              NotificationPermissionSection(appState: appState)
            }
            if accessibilityNeedsAction {
              AccessibilityPermissionSection(appState: appState)
            }
          }
        }

        if hasSupportingActions {
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            Text(PermissionsPageChrome.supportingSectionTitle)
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(Ink.secondary)
            VStack(spacing: OmiSpacing.xl) {
              if bluetoothNeedsAction {
                BluetoothPermissionSection(appState: appState)
              }
              if fullDiskAccessNeedsAction {
                FullDiskAccessPermissionSection(appState: appState)
              }
              if automationNeedsAction {
                AutomationPermissionSection(appState: appState)
              }
            }
          }
        }

        if hasGrantedPermissions {
          SettingsGlassSection(title: hasActionablePermissions ? "Granted" : nil) {
            grantedList
          }
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
      appState.refreshPermissionsForSettingsPage()
      // The user is most likely to grant something while this page is open, and most likely to
      // do it without leaving System Settings, so listen for the system's own signal rather
      // than waiting for Omi to be activated again.
      appState.startAccessibilityChangeObserver()
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      // Auto-refresh when app becomes active (user may have granted permission in System Settings)
      appState.refreshPermissionsForSettingsPage()
    }
  }

  private var header: some View {
    HStack(spacing: OmiSpacing.md) {
      if let symbol = PermissionsPageChrome.headerSymbol(allRequiredGranted: allRequiredGranted) {
        Image(systemName: symbol)
          .font(.system(size: 22, weight: .semibold))
          .foregroundColor(Ink.listeningGreen)
      }

      Text(PermissionsPageChrome.headerTitle)
        .inkStyle(.stepHeadline, color: Ink.primary)
    }
    .accessibilityElement(children: .combine)
    .accessibilityIdentifier(allRequiredGranted ? "permissions.header.settled" : "permissions.header.attention")
  }

  private var allGrantedBanner: some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: "checkmark.circle.fill")
        .scaledFont(size: OmiType.heading)
        .foregroundColor(Ink.listeningGreen)

      Text(PermissionsPageChrome.allGrantedMessage)
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
    .accessibilityElement(children: .combine)
    .accessibilityIdentifier("permissions.success-banner")
    .accessibilityLabel(PermissionsPageChrome.allGrantedMessage)
  }

  @ViewBuilder private var grantedList: some View {
    let granted = grantedKinds
    ForEach(Array(granted.enumerated()), id: \.element) { index, kind in
      grantedSection(kind)
      if index < granted.count - 1 {
        SettingsRowDivider()
      }
    }
  }

  private var grantedKinds: [PermissionKind] {
    var kinds: [PermissionKind] = []
    if !microphoneNeedsAction { kinds.append(.microphone) }
    if !screenRecordingNeedsAction { kinds.append(.screenRecording) }
    if showsSystemAudio, !systemAudioNeedsAction { kinds.append(.systemAudio) }
    if !notificationsNeedAction { kinds.append(.notifications) }
    if !accessibilityNeedsAction { kinds.append(.accessibility) }
    if showsBluetooth, !bluetoothNeedsAction { kinds.append(.bluetooth) }
    if !fullDiskAccessNeedsAction { kinds.append(.fullDiskAccess) }
    if !automationNeedsAction { kinds.append(.automation) }
    return kinds
  }

  @ViewBuilder private func grantedSection(_ kind: PermissionKind) -> some View {
    switch kind {
    case .microphone:
      MicrophonePermissionSection(appState: appState)
    case .screenRecording:
      ScreenRecordingPermissionSection(appState: appState)
    case .systemAudio:
      SystemAudioPermissionSection(appState: appState)
    case .notifications:
      NotificationPermissionSection(appState: appState)
    case .accessibility:
      AccessibilityPermissionSection(appState: appState)
    case .bluetooth:
      BluetoothPermissionSection(appState: appState)
    case .fullDiskAccess:
      FullDiskAccessPermissionSection(appState: appState)
    case .automation:
      AutomationPermissionSection(appState: appState)
    }
  }
}

private enum PermissionKind: String, Hashable {
  case microphone
  case screenRecording
  case systemAudio
  case notifications
  case accessibility
  case bluetooth
  case fullDiskAccess
  case automation
}

// MARK: - Shared row chrome

/// An unanswered or refused permission: the instructions stay visible. There is no chevron, because
/// collapsing a card whose only job is to get the grant does nothing useful.
@MainActor private struct PermissionActionCard<Badge: View, Detail: View>: View {
  let symbol: String
  let iconColor: Color
  let iconBackground: Color
  let title: String
  let description: String
  var descriptionColor: Color = Ink.secondary
  let borderColor: Color
  var fillColor: Color = Ink.wash
  var borderWidth: CGFloat = 1
  @ViewBuilder var badge: () -> Badge
  @ViewBuilder var detail: () -> Detail

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack(alignment: .center, spacing: OmiSpacing.lg) {
        ZStack {
          Circle()
            .fill(iconBackground)
            .frame(width: 48, height: 48)

          Image(systemName: symbol)
            .scaledFont(size: OmiType.heading)
            .foregroundColor(iconColor)
        }

        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          HStack(spacing: OmiSpacing.sm) {
            Text(title)
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(Ink.primary)
            badge()
          }

          Text(description)
            .scaledFont(size: OmiType.body)
            .foregroundColor(descriptionColor)
            .fixedSize(horizontal: false, vertical: true)
        }

        Spacer(minLength: 0)
      }
      .padding(OmiSpacing.xl)

      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        GlassSeparator()
        detail()
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.bottom, OmiSpacing.xl)
    }
    .background(
      RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
        .fill(fillColor)
        .overlay(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
            .stroke(borderColor, lineWidth: borderWidth)
        )
    )
  }
}

/// A settled permission: the same row shape the rest of Settings uses, with a status chip and no
/// disclosure. Expanding a granted row used to reveal an empty pane.
@MainActor private struct PermissionGrantedRow<Trailing: View>: View {
  let icon: String
  let title: String
  let subtitle: String
  var chipText: String = "Granted"
  var chipTint: Color = Ink.listeningGreen
  @ViewBuilder var trailing: () -> Trailing

  var body: some View {
    SettingsGlassRow(icon: icon, title: title, subtitle: subtitle) {
      HStack(spacing: OmiSpacing.sm) {
        SettingsStatusChip(text: chipText, tint: chipTint)
        trailing()
      }
    }
  }
}

extension PermissionGrantedRow where Trailing == EmptyView {
  init(
    icon: String, title: String, subtitle: String, chipText: String = "Granted", chipTint: Color = Ink.listeningGreen
  ) {
    self.init(
      icon: icon, title: title, subtitle: subtitle, chipText: chipText, chipTint: chipTint,
      trailing: { EmptyView() })
  }
}

@MainActor private struct PermissionCompactActionButton: View {
  let title: String
  var systemImage: String?
  var isBusy: Bool = false
  var action: () -> Void

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xs) {
        if isBusy {
          ProgressView()
            .scaleEffect(0.6)
            .frame(width: 12, height: 12)
        } else if let systemImage {
          Image(systemName: systemImage)
            .scaledFont(size: OmiType.caption)
        }
        Text(title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
      }
      .foregroundColor(Ink.primary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.xs)
      .background(
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
          .fill(Ink.rowFill)
          .overlay(
            RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
              .stroke(Ink.hairline, lineWidth: 1)
          )
      )
    }
    .buttonStyle(.plain)
    .disabled(isBusy)
  }
}

// MARK: - Microphone Permission Section
struct MicrophonePermissionSection: View {
  @ObservedObject var appState: AppState
  @State private var isResetting = false
  @State private var resetButtonText = "Reset & Restart"

  // Check if permission was explicitly denied (not just "not determined")
  private var isPermissionDenied: Bool {
    return appState.isMicrophonePermissionDenied()
  }

  // Colors based on state. A refuse is still "Not Granted" in the chip; the reset
  // instructions below are what macOS requires, not a second status colour.
  private var iconBackgroundColor: Color {
    if appState.hasMicrophonePermission {
      return Ink.listeningGreen.opacity(0.15)
    } else {
      return Ink.rowFill
    }
  }

  private var iconColor: Color {
    if appState.hasMicrophonePermission {
      return Ink.listeningGreen
    } else {
      return Ink.secondary
    }
  }

  private var borderColor: Color {
    if appState.hasMicrophonePermission {
      return Ink.listeningGreen.opacity(0.3)
    } else {
      return Ink.hairline
    }
  }

  var body: some View {
    if appState.hasMicrophonePermission {
      PermissionGrantedRow(
        icon: "mic.fill",
        title: "Microphone",
        subtitle: "Required for voice recording and transcription")
    } else {
      PermissionActionCard(
        symbol: isPermissionDenied ? "mic.slash.fill" : "mic.fill",
        iconColor: iconColor,
        iconBackground: iconBackgroundColor,
        title: "Microphone",
        description: isPermissionDenied
          ? "Reset required to try again"
          : "Required for voice recording and transcription",
        descriptionColor: Ink.secondary,
        borderColor: borderColor,
        fillColor: Ink.wash,
        badge: { microphoneStatusBadge },
        detail: {
          if isPermissionDenied {
            deniedStateContent
          } else {
            notDeterminedStateContent
          }
        }
      )
    }
  }

  // Status badge for microphone
  private var microphoneStatusBadge: some View {
    statusBadge(isGranted: appState.hasMicrophonePermission)
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
            Text("Find \"Omi\" and toggle it ON")
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
            "If no dialog appears, find \"\(Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Omi")\" in Settings and enable it"
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

  var body: some View {
    if appState.hasScreenRecordingPermission && !appState.isScreenRecordingStale {
      PermissionGrantedRow(
        icon: "rectangle.inset.filled.and.person.filled",
        title: "Screen Recording",
        subtitle: "Required for proactive monitoring and context awareness")
    } else {
      PermissionActionCard(
        symbol: appState.isScreenRecordingStale
          ? "rectangle.on.rectangle.slash" : "rectangle.inset.filled.and.person.filled",
        iconColor: appState.isScreenRecordingStale
          ? Ink.errorRed : Ink.secondary,
        iconBackground: appState.isScreenRecordingStale
          ? Ink.errorRed.opacity(0.15) : Ink.rowFill,
        title: "Screen Recording",
        description: appState.isScreenRecordingStale
          ? "Permission needs re-enabling after app update"
          : "Required for proactive monitoring and context awareness",
        descriptionColor: appState.isScreenRecordingStale ? Ink.errorRed : Ink.secondary,
        borderColor: appState.isScreenRecordingStale
          ? Ink.errorRed.opacity(0.5) : Ink.hairline,
        fillColor: appState.isScreenRecordingStale ? Ink.errorRed.opacity(0.05) : Ink.wash,
        borderWidth: appState.isScreenRecordingStale ? 2 : 1,
        badge: {
          if appState.isScreenRecordingStale {
            SettingsStatusChip(text: "Re-enable Required", tint: Ink.errorRed)
          } else {
            statusBadge(isGranted: false)
          }
        },
        detail: {
          if appState.isScreenRecordingStale {
            stalePermissionContent
          } else {
            normalGrantContent
          }
        }
      )
    }
  }

  // Content for STALE state - developer signing changed, user must remove and re-add
  private var stalePermissionContent: some View {
    let appName = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Omi"
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
            Text("Come back to Omi and grant the permission")
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
    let appName = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Omi"
    return VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("How to grant screen recording access:")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.primary)

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        instructionStep(number: 1, text: "Click \"Open Settings\" below - this will make Omi appear in the list")
        instructionStep(number: 2, text: "Find \"\(appName)\" in the Screen Recording list")
        instructionStep(number: 3, text: "Toggle the switch to enable screen recording")
        instructionStep(number: 4, text: "Return to Omi - permission will update automatically")
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
  @State private var isTesting = false

  private var status: SystemAudioPermissionStatus {
    appState.systemAudioPermissionStatus
  }

  private var isGranted: Bool {
    status == .granted
  }

  private var needsAction: Bool {
    PermissionsPageChrome.systemAudioNeedsAction(status: status)
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
    if needsAction {
      PermissionActionCard(
        symbol: isGranted ? "speaker.wave.2.fill" : "speaker.slash.fill",
        iconColor: iconColor,
        iconBackground: iconBackgroundColor,
        title: "System Audio",
        description: descriptionText,
        descriptionColor: status == .denied ? SettingsInk.notice : Ink.secondary,
        borderColor: borderColor,
        borderWidth: status == .denied ? 2 : 1,
        badge: { systemAudioStatusBadge },
        detail: { expandedContent }
      )
    } else {
      PermissionGrantedRow(
        icon: "speaker.wave.2.fill",
        title: "System Audio",
        subtitle: descriptionText,
        chipText: grantedChipText,
        chipTint: grantedChipTint
      ) {
        if status == .granted {
          PermissionCompactActionButton(
            title: "Test Again",
            systemImage: "speaker.wave.2.fill",
            isBusy: isTesting,
            action: testSystemAudioAccess)
        }
      }
    }
  }

  private var grantedChipText: String {
    switch status {
    case .granted: return PermissionsPageChrome.grantedStatusText
    case .unsupported: return "Unsupported"
    case .denied: return PermissionsPageChrome.missingStatusText
    case .unknown: return "Unknown"
    }
  }

  private var grantedChipTint: Color {
    switch status {
    case .granted: return Ink.listeningGreen
    case .denied: return SettingsInk.notice
    case .unsupported, .unknown: return Ink.secondary
    }
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
    case .granted:
      return SettingsStatusChip(text: PermissionsPageChrome.grantedStatusText, tint: Ink.listeningGreen)
    case .denied:
      return SettingsStatusChip(text: PermissionsPageChrome.missingStatusText, tint: SettingsInk.notice)
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
          Text("Test Access")
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

  // Check if permission was explicitly denied
  private var isPermissionDenied: Bool {
    return appState.isNotificationPermissionDenied()
  }

  // Colors based on state. A refuse is still "Not Granted" in the chip; System Settings
  // is the recovery path, not a second status colour.
  private var iconBackgroundColor: Color {
    if appState.hasNotificationPermission {
      return Ink.listeningGreen.opacity(0.15)
    } else {
      return Ink.rowFill
    }
  }

  private var iconColor: Color {
    if appState.hasNotificationPermission {
      return Ink.listeningGreen
    } else {
      return Ink.secondary
    }
  }

  private var borderColor: Color {
    if appState.hasNotificationPermission {
      return Ink.listeningGreen.opacity(0.3)
    } else {
      return Ink.hairline
    }
  }

  var body: some View {
    if appState.hasNotificationPermission {
      PermissionGrantedRow(
        icon: "bell.fill",
        title: "Notifications",
        subtitle: "Required for proactive assistant alerts")
    } else {
      PermissionActionCard(
        symbol: isPermissionDenied ? "bell.slash.fill" : "bell.fill",
        iconColor: iconColor,
        iconBackground: iconBackgroundColor,
        title: "Notifications",
        description: isPermissionDenied
          ? "Enable in System Settings to try again"
          : "Required for proactive assistant alerts",
        descriptionColor: Ink.secondary,
        borderColor: borderColor,
        fillColor: Ink.wash,
        badge: { notificationStatusBadge },
        detail: {
          if isPermissionDenied {
            deniedStateContent
          } else {
            notDeterminedStateContent
          }
        }
      )
    }
  }

  // Status badge for notifications
  private var notificationStatusBadge: some View {
    statusBadge(isGranted: appState.hasNotificationPermission)
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
          text: "Tip: In System Settings > Notifications > Omi, set style to \"Banners\" to see visual alerts")
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

// MARK: - Accessibility Permission Section

/// Accessibility is what lets Omi read *what* the user is looking at — the URL of the tab, the
/// path of the open document — rather than only that some window was frontmost. Without it the
/// work index still records every visit, but every handle degrades to the window title it was
/// meant to replace, and nothing anywhere says so.
///
/// Three states, because macOS has three. Ungranted is the ordinary ask. Granted-and-working is
/// a compact row. Granted-but-broken is its own thing: TCC reports the toggle on while the AX
/// calls behind it fail, which is what an app update or a re-sign leaves behind, and the switch
/// in System Settings looks correct the whole time. That state needs remove-and-re-add, not
/// another grant, so it says so.
struct AccessibilityPermissionSection: View {
  @ObservedObject var appState: AppState

  var body: some View {
    if appState.hasAccessibilityPermission && !appState.isAccessibilityBroken {
      PermissionGrantedRow(
        icon: "accessibility",
        title: "Accessibility",
        subtitle: "Lets Omi identify the document, page, or file you are working in")
    } else {
      PermissionActionCard(
        symbol: appState.isAccessibilityBroken ? "exclamationmark.triangle.fill" : "accessibility",
        iconColor: appState.isAccessibilityBroken ? Ink.errorRed : Ink.secondary,
        iconBackground: appState.isAccessibilityBroken ? Ink.errorRed.opacity(0.15) : Ink.rowFill,
        title: "Accessibility",
        description: appState.isAccessibilityBroken
          ? "Permission needs re-enabling after app update"
          : "Lets Omi identify the document, page, or file you are working in",
        descriptionColor: appState.isAccessibilityBroken ? Ink.errorRed : Ink.secondary,
        borderColor: appState.isAccessibilityBroken ? Ink.errorRed.opacity(0.5) : Ink.hairline,
        fillColor: appState.isAccessibilityBroken ? Ink.errorRed.opacity(0.05) : Ink.wash,
        borderWidth: appState.isAccessibilityBroken ? 2 : 1,
        badge: {
          if appState.isAccessibilityBroken {
            SettingsStatusChip(text: "Re-enable Required", tint: Ink.errorRed)
          } else {
            statusBadge(isGranted: false)
          }
        },
        detail: {
          if appState.isAccessibilityBroken {
            brokenGrantContent
          } else {
            normalGrantContent
          }
        }
      )
    }
  }

  private var appName: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Omi"
  }

  private var normalGrantContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("Without this, Omi can see that you were in an app, but not which page or file.")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)

      Text("How to grant accessibility access:")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.primary)

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        instructionStep(number: 1, text: "Click \"Grant Access\" below")
        instructionStep(number: 2, text: "Find \"\(appName)\" in the Accessibility list")
        instructionStep(number: 3, text: "Toggle the switch to enable accessibility")
        instructionStep(number: 4, text: "Return to Omi - permission will update automatically")
      }

      Button(action: { appState.triggerAccessibilityPermission() }) {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "checkmark.shield")
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
      .accessibilityIdentifier("permissions.accessibility.grant")
    }
  }

  /// The toggle already looks enabled, so "grant it again" is the one instruction that cannot
  /// work. Removing the stale entry is what re-arms the grant against the new signature.
  private var brokenGrantContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text("Accessibility looks enabled, but the permission stopped working after an app update.")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        HStack(alignment: .top, spacing: OmiSpacing.md) {
          Text("1")
            .scaledFont(size: OmiType.caption, weight: .bold)
            .foregroundColor(Ink.surface)
            .frame(width: 22, height: 22)
            .background(Circle().fill(Ink.primary))

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            Text("Open Accessibility settings")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)

            Button(action: { appState.openAccessibilityPreferences() }) {
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
            .accessibilityIdentifier("permissions.accessibility.open-settings")
          }
        }

        instructionStep(number: 2, text: "Find \"\(appName)\" in the Accessibility list")
        instructionStep(
          number: 3, text: "Click on \"\(appName)\", then click the minus (\u{2212}) button to remove it")
        instructionStep(number: 4, text: "Add \(appName) back with the plus (+) button and toggle it on")
      }
    }
  }
}

// MARK: - Supporting Permission Sections

/// One shape for the three permissions that unlock a single feature each. They have no stale or
/// broken variant modelled, no prompt API worth calling from here, and nothing to say beyond
/// what they enable and where the switch lives — so they share one card rather than three
/// near-identical ones.
@MainActor private struct SupportingPermissionSection: View {
  let granted: Bool
  let icon: String
  let title: String
  let subtitle: String
  let steps: [String]
  let openSettings: () -> Void
  var identifier: String

  var body: some View {
    if granted {
      PermissionGrantedRow(icon: icon, title: title, subtitle: subtitle)
    } else {
      PermissionActionCard(
        symbol: icon,
        iconColor: Ink.secondary,
        iconBackground: Ink.rowFill,
        title: title,
        description: subtitle,
        borderColor: Ink.hairline,
        badge: { statusBadge(isGranted: false) },
        detail: {
          VStack(alignment: .leading, spacing: OmiSpacing.lg) {
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                instructionStep(number: index + 1, text: step)
              }
            }

            Button(action: openSettings) {
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
            .accessibilityIdentifier(identifier)
          }
        }
      )
    }
  }
}

/// How Omi talks to the physical wearable at all — `BluetoothManager` opens a `CBCentralManager`
/// to scan and connect. Denial breaks pairing and device audio with nothing else to show for it.
struct BluetoothPermissionSection: View {
  @ObservedObject var appState: AppState

  var body: some View {
    SupportingPermissionSection(
      granted: appState.hasBluetoothPermission,
      icon: "wave.3.right",
      title: "Bluetooth",
      subtitle: "Needed to pair and record with an Omi device",
      steps: [
        "Click \"Open Settings\" below",
        "Find \"\(AppBuild.displayName)\" in the Bluetooth list",
        "Toggle the switch on, then return to Omi",
      ],
      openSettings: { appState.openBluetoothPreferences() },
      identifier: "permissions.bluetooth.open-settings")
  }
}

/// Reads Apple Notes for memories, and backs the chat agent's file scan. Feature-scoped, but a
/// revocation is otherwise only discoverable by asking the assistant and watching it fail.
struct FullDiskAccessPermissionSection: View {
  @ObservedObject var appState: AppState

  var body: some View {
    SupportingPermissionSection(
      granted: appState.hasFullDiskAccess,
      icon: "folder",
      title: "Full Disk Access",
      subtitle: "Lets Omi read Apple Notes and search your files when you ask",
      steps: [
        "Click \"Open Settings\" below",
        "Find \"\(AppBuild.displayName)\" in the Full Disk Access list",
        "Toggle the switch on, then return to Omi",
      ],
      openSettings: { appState.openFullDiskAccessPreferences() },
      identifier: "permissions.full-disk-access.open-settings")
  }
}

/// Drives the System Events AppleScript paths. The narrowest of the three, and the one most
/// likely to be denied by a user who clicked through a prompt once and never saw it again.
struct AutomationPermissionSection: View {
  @ObservedObject var appState: AppState

  var body: some View {
    SupportingPermissionSection(
      granted: appState.hasAutomationPermission,
      icon: "gearshape.2",
      title: "Automation",
      subtitle: "Lets Omi ask System Events about the app you are in",
      steps: [
        "Click \"Open Settings\" below",
        "Find \"\(AppBuild.displayName)\" in the Automation list",
        "Enable \"System Events\" beneath it, then return to Omi",
      ],
      openSettings: { appState.openAutomationPreferences() },
      identifier: "permissions.automation.open-settings")
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
    text: PermissionsPageChrome.statusChipText(granted: isGranted),
    tint: isGranted ? Ink.listeningGreen : SettingsInk.notice)
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
