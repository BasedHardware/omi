import AppKit
import ApplicationServices
import Foundation

/// Asks an Electron app to publish its accessibility tree.
///
/// Electron, like the Chromium it is built on, keeps that tree off by default because
/// building and maintaining one costs the app memory and CPU. It is turned on when an
/// assistive client asks for it, and `AXManualAccessibility` is the attribute Electron
/// added for exactly that — the alternative, `AXEnhancedUserInterface`, is the flag
/// VoiceOver sets, and setting it breaks window managers, so it is not ours to use.
///
/// Without this, Slack, Discord, VS Code, Notion and everything else built on Electron
/// report an empty tree: form assist finds no fields, the draft card finds no compose
/// box, and a spoken lookup reads nothing off the window.
///
/// Asked once per process and left on. The tree takes a moment to build after the
/// request, so this runs when the user switches to the app rather than when something
/// needs the tree — by then it is warm. Toggling it per scan would make the app rebuild
/// the tree each time, which is worse for them than leaving it up.
@MainActor
enum ElectronAccessibility {
  /// Processes already asked. Bounded because it is only ever an optimisation: asking a
  /// second time is harmless, so the set may be dropped rather than grown without limit.
  private static var asked: Set<pid_t> = []
  private static let maxTracked = 64

  static func requestTree(for app: NSRunningApplication) {
    let pid = app.processIdentifier
    guard pid != ProcessInfo.processInfo.processIdentifier else { return }
    guard !asked.contains(pid), AXIsProcessTrusted(), isElectron(app.bundleURL) else { return }
    if asked.count >= maxTracked { asked.removeAll() }
    asked.insert(pid)

    let result = AXUIElementSetAttributeValue(
      AXUIElementCreateApplication(pid),
      "AXManualAccessibility" as CFString,
      kCFBooleanTrue)
    // Best effort by design: some Electron versions report the attribute as unsupported.
    // Nothing downstream may depend on this succeeding — the tree is read the same way
    // either way, and a dark one still has the window's picture behind it.
    log(
      "ElectronAccessibility: asked \(app.localizedName ?? "app") to publish its tree"
        + " (\(result == .success ? "accepted" : "unsupported"))")
  }

  /// An Electron app carries the framework it is built on inside its bundle. Checked
  /// rather than guessed from the name, and never inferred from Chromium alone: a
  /// Chromium browser ignores this attribute and needs the VoiceOver flag we will not set.
  nonisolated static func isElectron(_ bundleURL: URL?) -> Bool {
    guard let bundleURL else { return false }
    return FileManager.default.fileExists(
      atPath:
        bundleURL
        .appendingPathComponent("Contents/Frameworks/Electron Framework.framework")
        .path)
  }
}
