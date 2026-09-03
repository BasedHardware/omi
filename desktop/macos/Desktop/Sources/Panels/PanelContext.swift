import AppKit
import ApplicationServices
import Foundation

/// What a panel is about, in the only terms the screen can tell us.
///
/// The window is not fine enough. A browser keeps one window and one window id across
/// every tab, so a panel bound to the window follows the user onto a page it knows
/// nothing about — the answers to a form they have navigated away from, still on screen,
/// still looking authoritative. The page URL is what separates one tab from the next,
/// and the window title is what separates one conversation from the next in apps that
/// rename themselves per thread.
struct PanelContext: Equatable, Sendable {
  let appName: String
  let windowID: CGWindowID?
  let windowTitle: String
  /// The frontmost page's URL when the app is a browser; empty for everything else, and
  /// empty when accessibility withholds it — in which case the title carries the tab.
  let pageURL: String

  /// How tightly a panel is bound to where it was opened.
  enum Grain: Sendable {
    /// The panel is about what is on screen — a form, a conversation. Anything that
    /// changes the page or the window changes the answer, so the panel goes.
    case context
    /// The panel is about the user, not the screen ("show me my email address"). Tabs
    /// are none of its business; leaving the app is.
    case app
  }

  /// `comparingPageURL` is off for the cheap check that runs on every accessibility
  /// event: a tab switch renames the window, so the title already answers it, and the
  /// tree walk the URL costs is not worth paying at that rate. The sweep runs the full
  /// comparison, which is what catches two tabs that happen to share a title.
  func matches(_ other: PanelContext, grain: Grain, comparingPageURL: Bool = true) -> Bool {
    guard appName == other.appName else { return false }
    guard grain == .context else { return true }
    // A window id is only comparable when both sides have one: a context read while Omi
    // held focus has no frontmost-window record, and the title still identifies the tab.
    if let mine = windowID, let theirs = other.windowID, mine != theirs { return false }
    guard windowTitle == other.windowTitle else { return false }
    guard comparingPageURL, !pageURL.isEmpty, !other.pageURL.isEmpty else { return true }
    return pageURL == other.pageURL
  }

  /// The frontmost window, or nil when Omi itself is in front — the panel takes clicks
  /// without activating the app, so "Omi is frontmost" is never the user leaving.
  @MainActor
  static func front(resolvePageURL: Bool = true) -> PanelContext? {
    guard let app = NSWorkspace.shared.frontmostApplication,
      app.processIdentifier != ProcessInfo.processInfo.processIdentifier
    else { return nil }
    return of(app: app, resolvePageURL: resolvePageURL)
  }

  /// One app's focused window, read by process id so it answers for an app that is no
  /// longer frontmost — which is the normal case while Omi's own voice UI has focus.
  @MainActor
  static func of(app: NSRunningApplication, resolvePageURL: Bool = true) -> PanelContext {
    let appName = app.localizedName ?? ""
    let isFront = NSWorkspace.shared.frontmostApplication?.processIdentifier == app.processIdentifier
    let info = isFront ? ScreenCaptureService.getActiveWindowInfo() : nil
    let appElement = AXUIElementCreateApplication(app.processIdentifier)
    let window = AXFormTree.elementAttribute(appElement, "AXFocusedWindow")
    let axTitle = window.map { AXFormTree.stringAttribute($0, "AXTitle") } ?? ""
    return PanelContext(
      appName: appName,
      windowID: info?.windowID,
      windowTitle: axTitle.isEmpty ? (info?.windowTitle ?? "") : axTitle,
      // Only browsers pay for the tree walk, and only they have tabs to tell apart.
      pageURL: resolvePageURL && MessageComposeGate.isBrowser(appName)
        ? window.map(AXFormTree.pageURL(inWindow:)) ?? "" : ""
    )
  }
}
