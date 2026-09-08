import AppKit
import ApplicationServices

/// Every permission row the Permissions page shows, as flat values a harness can assert on.
///
/// It lives outside `DesktopAutomationBridge` because that file is line-count ratcheted against
/// `main`, and because a snapshot of permission state is a thing worth reading on its own rather
/// than a closure buried in a registration table.
///
/// `missing` comes straight from `AppState.missingPermissions`, which is the point: a permission
/// the app can report missing and the page cannot show is a divergence this makes visible to a
/// test rather than only to someone scrolling the pane.
enum PermissionsSnapshot {
  static func capture() async -> [String: String] {
    guard let appState = await MainActor.run(body: { AppState.current }) else {
      return ["error": "app state unavailable"]
    }
    // Probe first. On a named dev bundle the accessibility flag is not read at startup, so a
    // snapshot taken without this reports the default rather than the machine.
    await MainActor.run { appState.refreshPermissionsForSettingsPage() }
    _ = await appState.refreshAccessibilityPermission()

    let axProbe = AppState.axProbeResult(targets: AppState.accessibilityProbeTargets())
    let axTrusted = AXIsProcessTrusted()
    let axSuppressed = ScreenCaptureService.isAccessibilitySuppressedForTesting()

    return await MainActor.run {
      [
        "microphone": granted(appState.hasMicrophonePermission),
        "screen_recording": appState.hasScreenRecordingPermission
          ? (appState.isScreenRecordingStale ? "stale" : "granted") : "not_granted",
        "system_audio": appState.systemAudioPermissionStatus.rawValue,
        "notifications": granted(appState.hasNotificationPermission),
        "accessibility": appState.hasAccessibilityPermission
          ? (appState.isAccessibilityBroken ? "broken" : "granted") : "not_granted",
        "bluetooth": granted(appState.hasBluetoothPermission),
        "full_disk_access": granted(appState.hasFullDiskAccess),
        "automation": granted(appState.hasAutomationPermission),
        "missing": appState.missingPermissions.joined(separator: ","),
        "ax_suppressed": axSuppressed ? "true" : "false",
        "ax_tcc_trusted": axTrusted ? "true" : "false",
        "ax_probe": axProbe.rawValue,
      ]
    }
  }

  private static func granted(_ value: Bool) -> String { value ? "granted" : "not_granted" }
}
