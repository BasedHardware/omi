import AppKit
import Foundation

/// Moves the app into /Applications when it is launched from a mounted DMG or an
/// App Translocation mount, then relaunches the installed copy.
///
/// Running off the DMG is what produced the beta-user trio of bugs this fixes:
/// - App Translocation gives the bundle a randomized path/identity every launch,
///   so TCC grants (Screen Recording, System Audio) never stick — System Settings
///   shows the "omi" toggle ON while `CGPreflightScreenCaptureAccess()` returns
///   false for the running copy, and onboarding keeps re-asking.
/// - "Reset onboarding" relaunches via `open <bundlePath>`, which for a DMG-resident
///   bundle re-reveals the DMG's "Drag to Applications to install" Finder window.
/// - Sparkle updates fail on the read-only volume.
enum AppInstaller {
  /// Escape hatch for harnesses that intentionally run from unusual paths.
  static let skipEnvironmentKey = "OMI_SKIP_INSTALL_GATE"

  /// True only for unambiguous not-installed locations: a mounted volume (DMG) or
  /// an App Translocation mount. Deliberately excludes ~/Downloads and dev
  /// checkouts so local builds and named test bundles are never touched.
  static func isInstallerLocation(_ bundlePath: String) -> Bool {
    let path = bundlePath.lowercased()
    return path.hasPrefix("/volumes/") || path.contains("/apptranslocation/")
  }

  /// Where this bundle should live once installed.
  static func installedURL(forBundleURL bundleURL: URL) -> URL {
    URL(fileURLWithPath: "/Applications").appendingPathComponent(bundleURL.lastPathComponent)
  }

  /// Whether the copy at the installer location should replace an existing installed
  /// copy. Never downgrade: if the installed build is the same or newer, launch it
  /// as-is instead of overwriting it with the (possibly old) DMG contents.
  static func shouldReplaceInstalled(installedBuild: String?, sourceBuild: String?) -> Bool {
    guard let installedBuild, !installedBuild.isEmpty else { return true }
    guard let sourceBuild, !sourceBuild.isEmpty else { return false }
    return sourceBuild.compare(installedBuild, options: .numeric) == .orderedDescending
  }

  /// Install to /Applications and relaunch when running from a DMG/translocated
  /// mount. Returns true when this process is being replaced and the caller must
  /// stop launching. Any failure logs and returns false so the app keeps running
  /// from the DMG exactly as before.
  static func moveToApplicationsIfNeeded() -> Bool {
    guard ProcessInfo.processInfo.environment[skipEnvironmentKey] == nil else { return false }
    let bundleURL = Bundle.main.bundleURL
    guard isInstallerLocation(bundleURL.path) else { return false }

    let destination = installedURL(forBundleURL: bundleURL)
    let fileManager = FileManager.default
    log("AppInstaller: running from \(bundleURL.path), installing to \(destination.path)")

    if fileManager.fileExists(atPath: destination.path) {
      // A same-bundle-id running copy would already have made SingleInstanceGuard
      // exit this process, so an existing installed copy here is not running.
      let installedBuild = build(atBundleURL: destination)
      let sourceBuild = build(atBundleURL: bundleURL)
      if !shouldReplaceInstalled(installedBuild: installedBuild, sourceBuild: sourceBuild) {
        log(
          "AppInstaller: installed copy (build \(installedBuild ?? "?")) is same or newer than "
            + "DMG copy (build \(sourceBuild ?? "?")) — launching it without overwriting")
        return relaunch(destination)
      }
      do {
        try fileManager.removeItem(at: destination)
      } catch {
        logError("AppInstaller: could not remove existing installed copy", error: error)
        showManualInstallHint()
        return false
      }
    }

    do {
      try fileManager.copyItem(at: bundleURL, to: destination)
    } catch {
      logError("AppInstaller: copy to /Applications failed", error: error)
      showManualInstallHint()
      return false
    }

    // Clear quarantine on the installed copy. The user already passed Gatekeeper's
    // first-open check to get this far; without this, the programmatic copy keeps
    // the quarantine xattr and macOS may translocate the /Applications copy too,
    // recreating the broken-TCC state this gate exists to fix.
    removeQuarantine(at: destination)

    return relaunch(destination)
  }

  private static func build(atBundleURL url: URL) -> String? {
    Bundle(url: url)?.object(forInfoDictionaryKey: "CFBundleVersion") as? String
  }

  private static func removeQuarantine(at url: URL) {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/bin/xattr")
    task.arguments = ["-dr", "com.apple.quarantine", url.path]
    do {
      try task.run()
      task.waitUntilExit()
    } catch {
      logError("AppInstaller: failed to clear quarantine", error: error)
    }
  }

  /// Launch the installed copy after this process exits (same delayed-`open`
  /// pattern as `AppState.restartApp()` so the single-instance lock is free by
  /// the time the new copy takes it).
  private static func relaunch(_ destination: URL) -> Bool {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/bin/sh")
    task.arguments = ["-c", "sleep 0.5 && open \"\(destination.path)\""]
    do {
      try task.run()
    } catch {
      logError("AppInstaller: failed to schedule relaunch of installed copy", error: error)
      return false
    }
    log("AppInstaller: installed to /Applications, relaunching from there")
    DispatchQueue.main.async {
      NSApplication.shared.terminate(nil)
    }
    return true
  }

  private static func showManualInstallHint() {
    DispatchQueue.main.async {
      let alert = NSAlert()
      alert.messageText = "Move omi to Applications"
      alert.informativeText =
        "omi is running from the installer image, so macOS permissions and updates won't work. "
        + "Drag omi to the Applications folder, then open it from there."
      alert.alertStyle = .warning
      alert.addButton(withTitle: "OK")
      alert.runModal()
    }
  }
}
