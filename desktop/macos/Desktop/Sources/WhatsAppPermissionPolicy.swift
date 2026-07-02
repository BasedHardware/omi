import AppKit
import ApplicationServices
import Foundation

/// Permission checks for the WhatsApp connector.
///
/// Two macOS TCC permissions matter:
///  - **Full Disk Access** to read the WhatsApp group-container database
///    (`ChatStorage.sqlite`). There is no API to query or prompt for it — we detect
///    it by attempting to open the file and guide the user to System Settings
///    (grant then Quit & Reopen).
///  - **Accessibility** to press Return in WhatsApp's compose box on the send path
///    (`WhatsAppSenderService`). We can query it without prompting via
///    `AXIsProcessTrustedWithOptions` and open the settings pane on demand.
enum WhatsAppPermissionPolicy {

  /// WhatsApp (Mac App Store / Catalyst) stores its SQLite DB in a shared group
  /// container. This is the live database backing the app's chats.
  static var chatDatabaseURL: URL {
    FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(
        "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite",
        isDirectory: false)
  }

  /// WhatsApp.app bundle id (Mac App Store Catalyst build).
  static let whatsappBundleID = "net.whatsapp.WhatsApp"

  // MARK: - Full Disk Access

  /// True when reading `ChatStorage.sqlite` is not blocked by Full Disk Access.
  /// Attempting the read is the only reliable probe. A *missing* database (the user
  /// never installed WhatsApp, or never signed in) is not a permission denial, so
  /// we treat it as "not blocked" — otherwise we'd wrongly tell the user to grant
  /// FDA. Only an actual access error (EPERM/EACCES from TCC) returns false.
  static func fullDiskAccessGranted() -> Bool {
    do {
      let handle = try FileHandle(forReadingFrom: chatDatabaseURL)
      defer { try? handle.close() }
      _ = try handle.read(upToCount: 1)
      return true
    } catch let error as NSError {
      if isMissingFileError(error) {
        return true
      }
      return false
    }
  }

  /// Whether `error` represents a genuinely absent file (ENOENT) rather than a
  /// permission denial. TCC denials surface as EPERM/EACCES, not "no such file".
  private static func isMissingFileError(_ error: NSError) -> Bool {
    if error.domain == NSCocoaErrorDomain && error.code == NSFileReadNoSuchFileError {
      return true
    }
    if error.domain == NSPOSIXErrorDomain && error.code == Int(ENOENT) {
      return true
    }
    if let underlying = error.userInfo[NSUnderlyingErrorKey] as? NSError {
      return isMissingFileError(underlying)
    }
    return false
  }

  static func openFullDiskAccessSettings() {
    // macOS lists an app under Full Disk Access only after the app itself has
    // *attempted* to read an FDA-protected file — the denied TCC access is what
    // inserts our row into the list. Opening this pane alone never adds us, so
    // trigger the database read first (result ignored). Then the user lands on a
    // list that already contains this app and only needs to flip the toggle.
    _ = fullDiskAccessGranted()

    // The Privacy panes snapshot their app list when the window loads and do NOT
    // refresh when a new app is registered while Settings is already open. If we
    // just registered above but Settings is already showing a stale list, the
    // user won't see our row. Quit the running instance so reopening rebuilds the
    // list fresh (with our just-added app). A cold Settings needs no such reset.
    let settingsApps = NSWorkspace.shared.runningApplications.filter {
      $0.bundleIdentifier == "com.apple.systempreferences"
    }
    let wasRunning = !settingsApps.isEmpty
    settingsApps.forEach { $0.terminate() }

    let openPane = {
      if let url = URL(
        string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
      {
        NSWorkspace.shared.open(url)
      }
    }
    if wasRunning {
      // Give the quit a moment to complete so the relaunch loads a fresh list.
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.4, execute: openPane)
    } else {
      openPane()
    }
  }

  // MARK: - Accessibility (send path)

  /// Whether this process is trusted for the Accessibility API, checked without
  /// prompting. Needed so `WhatsAppSenderService` can press Return in WhatsApp's
  /// compose box after prefilling a reply.
  static func accessibilityGranted() -> Bool {
    let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: false] as CFDictionary
    return AXIsProcessTrustedWithOptions(options)
  }

  static func openAccessibilitySettings() {
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
    {
      NSWorkspace.shared.open(url)
    }
  }
}
