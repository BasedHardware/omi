import AppKit
import Foundation

/// Permission checks for the iMessage connector.
///
/// Two macOS TCC permissions matter:
///  - **Full Disk Access** to read `~/Library/Messages/chat.db`. There is no API
///    to query or prompt for it — we detect it by attempting to open the file and
///    guide the user to System Settings (grant then Quit & Reopen).
///  - **Automation / Apple Events** to send via Messages.app (used in Phase 3).
///    The app already ships the `apple-events` entitlement, so the first send
///    triggers the standard per-target TCC prompt.
enum IMessagePermissionPolicy {

  static var chatDatabaseURL: URL {
    FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Messages/chat.db", isDirectory: false)
  }

  /// Messages.app bundle id, resolved at runtime (historically `com.apple.MobileSMS`).
  static var messagesBundleID: String {
    if let bundle = Bundle(path: "/System/Applications/Messages.app"),
      let id = bundle.bundleIdentifier
    {
      return id
    }
    return "com.apple.MobileSMS"
  }

  // MARK: - Full Disk Access

  /// True if we can actually read chat.db. Attempting the read is the only
  /// reliable probe — `FileManager` cannot distinguish "denied" from "missing".
  static func fullDiskAccessGranted() -> Bool {
    do {
      let handle = try FileHandle(forReadingFrom: chatDatabaseURL)
      defer { try? handle.close() }
      _ = try handle.read(upToCount: 1)
      return true
    } catch {
      return false
    }
  }

  static func openFullDiskAccessSettings() {
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
    {
      NSWorkspace.shared.open(url)
    }
  }

  // MARK: - Messages automation (Apple Events)

  /// TCC automation status for Messages without prompting. `noErr` = granted,
  /// `-1743` = denied, `-1744` = not yet determined.
  static func messagesAutomationStatus() -> OSStatus {
    var addressDesc = AEAddressDesc()
    return messagesBundleID.withCString { cString in
      AECreateDesc(typeApplicationBundleID, cString, strlen(cString), &addressDesc)
      let result = AEDeterminePermissionToAutomateTarget(
        &addressDesc, typeWildCard, typeWildCard, false)
      AEDisposeDesc(&addressDesc)
      return result
    }
  }

  static func messagesAutomationGranted() -> Bool {
    messagesAutomationStatus() == noErr
  }

  static func openAutomationSettings() {
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")
    {
      NSWorkspace.shared.open(url)
    }
  }
}
