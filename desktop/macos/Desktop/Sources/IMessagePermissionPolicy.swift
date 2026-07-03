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

  /// True when reading chat.db is not blocked by Full Disk Access. Attempting the
  /// read is the only reliable probe. A *missing* chat.db (the user never used
  /// iMessage) is not a permission denial, so we treat it as "not blocked" —
  /// otherwise we'd wrongly tell the user to grant FDA. Only an actual access
  /// error (EPERM/EACCES from TCC) returns false.
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
    // trigger the chat.db read first. Then the user lands on a list that already
    // contains this app and only needs to flip the toggle, instead of an empty list
    // where they'd have to hunt for the app with "+".
    let granted = fullDiskAccessGranted()

    let openPane = {
      if let url = URL(
        string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
      {
        NSWorkspace.shared.open(url)
      }
    }

    // When access is already available (or chat.db is absent), the probe added no new
    // row, so there is nothing to refresh — don't terminate a Settings window the user
    // may have open for something else. Just open the pane.
    guard !granted else {
      openPane()
      return
    }

    // The Privacy panes snapshot their app list when the window loads and do NOT
    // refresh when a new app is registered while Settings is already open. If we just
    // registered above but Settings is showing a stale list, the user won't see our
    // row. Quit the running instance so reopening rebuilds the list fresh.
    let workspace = NSWorkspace.shared
    let settingsApps = workspace.runningApplications.filter {
      $0.bundleIdentifier == "com.apple.systempreferences"
    }
    guard !settingsApps.isEmpty else {
      openPane()  // cold Settings needs no reset
      return
    }

    // Reopen the pane only once the old instance has actually terminated — observed via
    // the workspace notification rather than a fixed delay (which could reopen against a
    // still-tearing-down instance and land on the stale list). A timeout fallback
    // guarantees the pane always opens even if the notification never arrives.
    var observer: NSObjectProtocol?
    var opened = false
    let finish = {
      guard !opened else { return }
      opened = true
      if let observer { workspace.notificationCenter.removeObserver(observer) }
      openPane()
    }
    observer = workspace.notificationCenter.addObserver(
      forName: NSWorkspace.didTerminateApplicationNotification, object: nil, queue: .main
    ) { note in
      let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication
      if app?.bundleIdentifier == "com.apple.systempreferences" { finish() }
    }
    settingsApps.forEach { $0.terminate() }
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5, execute: finish)
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
