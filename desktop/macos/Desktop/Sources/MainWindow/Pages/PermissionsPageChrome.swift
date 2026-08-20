import Foundation

/// The nav glyph for Permissions. A lock, not a warning: the page can still shout when a grant
/// is missing, but the row that opens it is just another settings destination.
enum PermissionNavSymbol {
  static let outline = "lock"
  static let filled = "lock.fill"
  /// Mark beside the Permissions label while a required grant is still missing.
  static let missingNotice = "exclamationmark.triangle.fill"
}

/// Presentation policy for the Permissions settings page.
///
/// Granted rows are a compact status list, not empty disclosures. The success banner is the
/// settled-state signal; the page title itself stays "Permissions" in both states.
enum PermissionsPageChrome {
  static let allGrantedMessage = "All permissions granted! Omi is ready to use."
  static let headerTitle = "Permissions"

  /// Settled state keeps the green check. Missing grants do not wear a warning glyph here —
  /// that mark lives on the sidebar row instead.
  static func headerSymbol(allRequiredGranted: Bool) -> String? {
    allRequiredGranted ? "checkmark.circle.fill" : nil
  }

  /// One status word for every missing grant. macOS still distinguishes *unanswered* from
  /// *refused* in the instructions (a refuse will not show the system prompt again), but the
  /// chip does not: "Denied" reads as a failure, and "Not Granted" is already the work to do.
  static let missingStatusText = "Not Granted"
  static let grantedStatusText = "Granted"

  static func statusChipText(granted: Bool) -> String {
    granted ? grantedStatusText : missingStatusText
  }

  static func microphoneNeedsAction(granted: Bool) -> Bool { !granted }

  static func screenRecordingNeedsAction(granted: Bool, stale: Bool) -> Bool {
    !granted || stale
  }

  static func notificationsNeedAction(granted: Bool) -> Bool { !granted }

  /// Unknown is still work: Core Audio has no preflight, so the row stays open for Test Access.
  /// A proven grant (or an OS that cannot do this) settles into the compact list.
  static func systemAudioNeedsAction(status: SystemAudioPermissionStatus) -> Bool {
    switch status {
    case .granted, .unsupported: return false
    case .unknown, .denied: return true
    }
  }

  /// Mirrors `AppState.missingPermissions`, which has counted Accessibility as required since
  /// before this page existed. A *broken* grant is work too: TCC reports the toggle on while
  /// the AX calls behind it fail, which is what a macOS update or an app re-sign leaves
  /// behind, and no amount of looking at the switch tells the user that.
  static func accessibilityNeedsAction(granted: Bool, broken: Bool) -> Bool {
    !granted || broken
  }

  static func bluetoothNeedsAction(granted: Bool) -> Bool { !granted }
  static func fullDiskAccessNeedsAction(granted: Bool) -> Bool { !granted }
  static func automationNeedsAction(granted: Bool) -> Bool { !granted }

  /// Permissions Omi cannot run without. Asserted equal to the universe of
  /// `AppState.missingPermissions`, because those two sets diverged once: Accessibility was
  /// required by the app and absent from the page, so the sidebar wore a warning that the page
  /// offered no way to clear, and "All permissions granted" was unreachable on a machine with
  /// nothing visibly wrong.
  static let requiredKinds: Set<String> = [
    "Microphone", "Screen Recording", "System Audio", "Notifications", "Accessibility",
  ]

  /// Permissions that unlock one feature each, rather than gating the app.
  ///
  /// They get a row because a revoked grant is otherwise invisible after onboarding — the probes
  /// run at every launch and nothing ever displays them. They deliberately stay out of
  /// `missingPermissions`: a user with no Omi wearable should not be told Bluetooth is missing,
  /// and a warning that cannot be resolved by anyone who does not want the feature is noise.
  static let supportingKinds: Set<String> = [
    "Bluetooth", "Full Disk Access", "Automation",
  ]

  static let supportingSectionTitle = "Optional"

  /// Every permission the page can act on.
  static var actionableKinds: Set<String> { requiredKinds.union(supportingKinds) }
}
