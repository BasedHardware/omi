import Foundation

/// A running app as the target step sees it: plain values, copied off
/// `NSRunningApplication` on the main actor.
struct UIAutomationRunningApp: Equatable, Sendable {
  let pid: pid_t
  let bundleID: String
  let localizedName: String?
  let bundleURL: URL?
  let isActive: Bool
}

struct UIAutomationTargetFailure: Error, Equatable, Sendable {
  let reason: String
  let message: String
  var candidatePIDs: [pid_t] = []
}

/// Which app a UI automation tool may read, and the floor of apps it never
/// reads. Every check is a set lookup over values Omi holds itself: the
/// bundle id the kernel approved, the pid and name the system reports, the
/// person's capture exclusions and the secure-input state. There is no
/// per-app logic here, only a safety floor.
enum UIAutomationTargetPolicy {
  /// Trimmed, lowercased and shaped like a bundle id, or nil. The model's
  /// argument is untrusted text; this is the only form that is compared.
  static func normalizedBundleID(_ raw: Any?) -> String? {
    guard let string = raw as? String else { return nil }
    let normalized = string.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let labels = normalized.split(separator: ".", omittingEmptySubsequences: false)
    let isLabel: (Substring) -> Bool = { label in
      !label.isEmpty
        && label.unicodeScalars.allSatisfy { ("a"..."z").contains($0) || ("0"..."9").contains($0) || $0 == "-" }
    }
    guard normalized.count <= 255, labels.count >= 2, labels.allSatisfy(isLabel) else { return nil }
    return normalized
  }

  /// The one running copy of `bundleID`. Never launches anything: launching
  /// an app is an action, and this tool only reads.
  static func resolve(bundleID: String, pid: pid_t?, running: [UIAutomationRunningApp])
    -> Result<UIAutomationRunningApp, UIAutomationTargetFailure>
  {
    let matches = running.filter { $0.bundleID.lowercased() == bundleID }
    if let pid {
      guard let match = matches.first(where: { $0.pid == pid }) else {
        return .failure(
          UIAutomationTargetFailure(
            reason: "target_mismatch", message: "Process \(pid) is not a running copy of \(bundleID).",
            candidatePIDs: matches.map(\.pid)))
      }
      return .success(match)
    }
    switch matches.count {
    case 0:
      return .failure(
        UIAutomationTargetFailure(
          reason: "app_not_running",
          message: "\(bundleID) is not running. Omi does not open apps to read them; ask the person to open it."))
    case 1:
      return .success(matches[0])
    default:
      return .failure(
        UIAutomationTargetFailure(
          reason: "ambiguous_app", message: "More than one copy of \(bundleID) is running. Pass pid.",
          candidatePIDs: matches.map(\.pid)))
    }
  }

  /// Why this app may not be read, checked in a fixed order, or nil.
  static func refusal(
    for app: UIAutomationRunningApp,
    ownPID: pid_t,
    isExcludedFromCapture: (String) -> Bool,
    isSecureInputActive: Bool
  ) -> UIAutomationTargetFailure? {
    let bundleID = app.bundleID.lowercased()
    // Reading our own tree from a background thread re-enters SwiftUI and traps.
    if !AccessibilityProcessBoundary.isForeignProcess(app.pid, ownProcessID: ownPID)
      || GeneratedUIAutomationSafetyFloor.refusedBundleIDPrefixes.contains(where: bundleID.hasPrefix)
    {
      return UIAutomationTargetFailure(reason: "refused_own_app", message: "Omi does not read its own windows.")
    }
    if GeneratedUIAutomationSafetyFloor.refusedBundleIDs.contains(bundleID) {
      return UIAutomationTargetFailure(
        reason: "refused_app",
        message: "Omi never reads this app: terminals, password managers and credential prompts are always refused.")
    }
    // Only an application bundle is a target. App extensions (a System
    // Settings pane, a widget), XPC view services (AutoFill, passkey sign-in,
    // open and save panels) and bare executables are UI hosted for another
    // app and get none of that app's checks.
    guard app.bundleURL?.pathExtension.lowercased() == "app" else {
      return UIAutomationTargetFailure(
        reason: "refused_not_an_app", message: "This process is not an application, so Omi does not read it.")
    }
    // Capture exclusion is keyed by display name, so an app with no name
    // cannot be checked against it and is refused rather than waved through.
    guard let name = app.localizedName?.trimmingCharacters(in: .whitespacesAndNewlines), !name.isEmpty else {
      return UIAutomationTargetFailure(
        reason: "refused_unnamed_app", message: "This app reports no name, so Omi cannot check the capture exclusions.")
    }
    if isExcludedFromCapture(name) {
      return UIAutomationTargetFailure(
        reason: "refused_excluded_app", message: "The person excluded this app from capture, so Omi does not read it.")
    }
    if isSecureInputActive, app.isActive {
      return UIAutomationTargetFailure(
        reason: "refused_secure_input",
        message: "A password is being typed in this app right now. Try again after it is entered.")
    }
    return nil
  }

  /// Electron and Chromium hide their elements until an assistive client
  /// asks. This is a check of the app's runtime from its own bundle layout,
  /// not knowledge of any particular app.
  static func assistiveTreeMode(
    bundleURL: URL?, fileExists: (String) -> Bool = { FileManager.default.fileExists(atPath: $0) },
    frameworks: (URL) -> [String] = {
      (try? FileManager.default.contentsOfDirectory(atPath: $0.path)) ?? []
    }
  ) -> AssistiveTreeMode {
    guard let bundleURL else { return .none }
    let frameworksURL = bundleURL.appendingPathComponent("Contents/Frameworks", isDirectory: true)
    if fileExists(frameworksURL.appendingPathComponent("Electron Framework.framework").path) { return .electron }
    for name in frameworks(frameworksURL) where name.hasSuffix(".framework") {
      let pak = frameworksURL.appendingPathComponent(name).appendingPathComponent(
        "Versions/Current/Resources/chrome_100_percent.pak")
      if fileExists(pak.path) { return .chromium }
    }
    return .none
  }

  /// The app whose open pane is checked before every read.
  static func isPaneChecked(_ bundleID: String) -> Bool {
    bundleID.lowercased() == GeneratedUIAutomationSafetyFloor.paneCheckedBundleID
  }
}
