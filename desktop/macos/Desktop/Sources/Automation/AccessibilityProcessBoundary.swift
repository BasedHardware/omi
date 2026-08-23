import Foundation

/// The one rule every accessibility read in this app has to obey: never aim it at ourselves.
///
/// `AXUIElementCopyAttributeValue` against **another** process is inter-process communication.
/// It is safe from any thread, which is why the capture pipeline reads window titles and browser
/// URLs off the main actor without ceremony.
///
/// Against **our own** process it is not IPC at all. The accessibility server materialises our
/// AppKit and SwiftUI elements in place, on whatever thread asked, which re-enters our own view
/// graph from a background thread. Under Swift 6 isolation checking a `@MainActor` binding getter
/// reached that way does not misbehave quietly — it traps:
///
///     _swift_task_checkIsolatedSwift → dispatch_assert_queue_fail → SIGTRAP
///
/// Observed exactly that way: with Accessibility granted and the Omi window frontmost, the
/// capture tick walked Omi's own accessibility tree looking for a document URL, evaluated
/// `ChatFirstShell.legacySelectionBinding` on a cooperative thread, and the process died. It
/// needs no unusual state — only the permission working and the user looking at Omi.
///
/// Nothing of value is lost by declining: Omi's own window is not one of the user's work sources,
/// and every caller here has a non-accessibility fallback that still names the window.
enum AccessibilityProcessBoundary {
  /// Whether an accessibility read against `processID` crosses a process boundary, and is
  /// therefore safe to perform from a background thread.
  static func isForeignProcess(
    _ processID: pid_t,
    ownProcessID: pid_t = ProcessInfo.processInfo.processIdentifier
  ) -> Bool {
    processID != ownProcessID
  }
}
