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
}
