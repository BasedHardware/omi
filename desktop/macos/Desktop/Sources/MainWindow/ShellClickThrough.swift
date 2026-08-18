//
//  ShellClickThrough.swift — the transparent shell window stops swallowing the desktop's clicks.
//
//  `ShellWindowChrome` makes the main window a transparent rectangle the size of the
//  glass. Leftover air — the rounded-corner triangles, the gaps between stacked panels — would
//  still be an invisible click sink: the window server routes every click to the window under the
//  cursor no matter what is drawn there. Same failure class as the notch panel's dead zone
//  (PR #11372), on the shell window.
//
//  Same mechanism, too: a view-level `hitTest` nil cannot make a window click-through, so the
//  window-level `ignoresMouseEvents` is kept in sync with the pointer — ignored over air,
//  interactive over content. "Content" is answered by `InkGlassHitRegions`: every glass surface
//  registers its live extent, and a modal barrier registers the whole host while it is up.
//
//  Drag lives on the visible top bar (`ShellWindowDragHandle`). Resizing survives via an
//  interactive rim along the window's frame edge, which is the visible panel edge.
//

import AppKit
import Combine
import OmiTheme

/// Pure policy: which points of the shell window own the pointer.
enum ShellClickThroughPolicy {
  /// Interactive band kept along the window's frame edge so the chrome-less, resizable window can
  /// still be resized. The glass fills the window (`DesktopWindowLayoutPolicy.windowInset` is 0),
  /// so this rim *is* the visible panel edge. Matches AppKit's effective resize zone.
  static let resizeRim: CGFloat = 8

  static func acceptsMouseHit(
    localPoint: NSPoint,
    windowSize: NSSize,
    isResizable: Bool,
    contentContains: (NSPoint) -> Bool
  ) -> Bool {
    if isResizable {
      let nearEdge =
        localPoint.x <= resizeRim || localPoint.x >= windowSize.width - resizeRim
        || localPoint.y <= resizeRim || localPoint.y >= windowSize.height - resizeRim
      if nearEdge { return true }
    }
    return contentContains(localPoint)
  }
}

/// Keeps the shell window's `ignoresMouseEvents` in sync with the pointer. One instance per shell
/// window, owned by `ShellWindowAttachmentView` so it binds to the exact `NSWindow` hosting the
/// shell and dies with it.
@MainActor
final class ShellMouseInterceptionSync {
  private nonisolated(unsafe) var monitors: [Any] = []
  private var pollingCancellable: AnyCancellable?
  private weak var window: NSWindow?

  init(window: NSWindow) {
    self.window = window
    let scheduleReconciliation: @Sendable () -> Void = { [weak self] in
      DispatchQueue.main.async { self?.sync() }
    }
    if let global = NSEvent.addGlobalMonitorForEvents(
      matching: [.mouseMoved, .leftMouseDragged],
      handler: { _ in scheduleReconciliation() })
    {
      monitors.append(global)
    }
    if let local = NSEvent.addLocalMonitorForEvents(
      matching: [.mouseMoved],
      handler: { event in
        scheduleReconciliation()
        return event
      })
    {
      monitors.append(local)
    }
    sync()
  }

  deinit {
    monitors.forEach(NSEvent.removeMonitor)
  }

  /// Restores the ordinary always-interactive window before the sync goes away (e.g. the
  /// automation harness snapshots/restores presentation): a window left with
  /// `ignoresMouseEvents == true` and nobody updating it is unreachable.
  func detach() {
    window?.ignoresMouseEvents = false
    window = nil
    pollingCancellable = nil
  }

  func sync() {
    guard let window else { return }
    setPollingActive(window.isVisible)
    let shouldIgnore = FloatingBarMouseInterceptionPolicy.shouldIgnoreMouseEvents(
      mouseLocation: NSEvent.mouseLocation,
      windowFrame: window.frame,
      isVisible: window.isVisible,
      acceptsMouseHit: { [weak window] local in
        guard let window else { return true }
        return ShellClickThroughPolicy.acceptsMouseHit(
          localPoint: local,
          windowSize: window.frame.size,
          isResizable: window.styleMask.contains(.resizable),
          contentContains: {
            // No registered surface means nothing can vouch for this window's content, so it stays
            // fully interactive rather than becoming a pass-through hole.
            guard InkGlassHitRegions.shared.hasSurfaces(in: window) else { return true }
            return InkGlassHitRegions.shared.containsPoint($0, in: window)
          })
      })
    if window.ignoresMouseEvents != shouldIgnore {
      window.ignoresMouseEvents = shouldIgnore
    }
  }

  private func setPollingActive(_ active: Bool) {
    guard active != (pollingCancellable != nil) else { return }
    pollingCancellable =
      active
      ? Timer.publish(every: 1.0 / 30.0, on: .main, in: .common)
        .autoconnect()
        .sink { [weak self] _ in self?.sync() }
      : nil
  }
}
