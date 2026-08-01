import Foundation

/// Recognises a browser window in a private / incognito session so Rewind can skip that
/// window alone, instead of forcing the user to exclude the whole browser and lose the
/// regular browsing context Rewind exists to keep (#6677).
///
/// Matching is scoped by bundle identifier and anchored to the end of the window title, per
/// `FC-meeting-trigger-title-identity-drift`: a title pattern must be bound to a known
/// browser process and kept alongside negative near-suffix cases, or a generic title starts
/// matching.
///
/// Suffixes were verified on macOS 25.5 by loading the same URL in a normal and a private
/// window of each browser and diffing the accessibility title. A browser whose marker has
/// not been measured is deliberately absent — a missing entry captures exactly as it does
/// today, while a guessed one would claim protection nobody observed.
///
/// The marker exists only in the accessibility title. When `ScreenCaptureService` cannot use
/// the Accessibility API it falls back to `kCGWindowName`, which was measured to carry the
/// page title alone — a private Safari window arrives as `p6.html` and a Chrome incognito
/// window as `New Incognito Tab`, with no marker to match. Detection therefore holds only
/// while Omi is trusted for Accessibility, the permission it already requires.
///
/// Two further gaps, all three resolving toward capture rather than a false sense of privacy:
/// a private window that has not loaded a page yet reports an empty title, and the markers
/// are the English localizations.
enum PrivateBrowsingWindow {
  private static let privateTitleSuffixes: [String: String] = [
    "com.apple.Safari": ", Private Browsing",
    "com.google.Chrome": " (Incognito)",
    "com.brave.Browser": " (Private)",
  ]

  static func isPrivate(windowTitle: String?, bundleIdentifier: String?) -> Bool {
    guard let bundleIdentifier,
      let suffix = privateTitleSuffixes[bundleIdentifier],
      let windowTitle
    else { return false }
    return windowTitle.hasSuffix(suffix)
  }
}
