import AppKit
import CoreGraphics
import Foundation

/// The window-server state the 1 Hz capture tick gates on, read **off** the main actor.
///
/// Every read behind this type is a synchronous round trip to the WindowServer, and the capture
/// poll takes them once a second for the life of the process. Measured on a 74-window desktop
/// (`sample <pid> 20 1`, app idle): `CGWindowListCopyWindowInfo` cost ~1.9 ms per call and the tick
/// made two of them, so the two gates together held the main thread for ~7 ms out of every second —
/// 141 of the 199 non-idle main-thread samples in a 20 s trace. That is longer than a 120 Hz frame,
/// once a second, forever: a dropped frame every second in any animation or scroll.
///
/// None of it needs the main actor. It is process-wide system state, the C APIs are thread-safe,
/// and the tick is already `async`, so the reads happen on a background executor and only the two
/// decisions come back. The main-actor reads that remain at the call site (`NSWorkspace`) are
/// main-thread API and measured at 0.000 ms.
struct ProactiveCaptureSystemProbe: Sendable {
  /// A system mode that makes ScreenCaptureKit refuse, or `nil` when capture may proceed.
  var specialSystemMode: ProactiveSpecialSystemMode?
  /// A conferencing app is sharing the screen right now.
  var isScreenShareActive: Bool
}

/// Why capture is being skipped this tick. A value rather than a `Bool` so the reason survives the
/// hop back to the main actor and is still what gets logged.
enum ProactiveSpecialSystemMode: Sendable, Equatable {
  /// Dock is frontmost — Exposé or Mission Control is up.
  case dockFrontmost
  /// A large unnamed Dock window — the Mission Control / Exposé overlay.
  case dockOverlay(width: Int, height: Int)
  case notificationCenter

  var logDescription: String {
    switch self {
    case .dockFrontmost:
      return "Dock is frontmost app (Exposé/Mission Control active)"
    case .dockOverlay(let width, let height):
      return "Dock overlay window detected (\(width)x\(height)) - Mission Control/Exposé"
    case .notificationCenter:
      return "Notification Center is active"
    }
  }
}

enum ProactiveCaptureSystemProbeReader {
  /// The Mission Control / Exposé / Notification Centre rules, pure over one
  /// `CGWindowListCopyWindowInfo` snapshot so they can be stated by a test without a window server.
  ///
  /// `dockIsFrontmost` is passed in because it comes from `NSWorkspace`, which the caller reads on
  /// the main actor — it is the one input here that is not in the window list.
  static func specialSystemMode(
    windowList: [[String: Any]],
    dockIsFrontmost: Bool
  ) -> ProactiveSpecialSystemMode? {
    if dockIsFrontmost { return .dockFrontmost }

    for window in windowList {
      guard let ownerName = window[kCGWindowOwnerName as String] as? String else { continue }

      // A Dock window with no name is the Mission Control / Exposé overlay — but only when it is
      // large enough to be the overlay rather than one of the Dock's own small chrome windows.
      if ownerName == "Dock" {
        let windowName = window[kCGWindowName as String] as? String
        if windowName == nil || windowName?.isEmpty == true {
          // The Dock also owns the full-screen desktop/wallpaper backstop, which sits at a
          // deeply negative window layer and is on screen for the life of the session. The
          // real Mission Control / Exposé overlay draws at a positive layer, above app
          // windows. Without the layer cut the backstop matches the size rule and capture
          // is skipped on every tick forever — no proactive analysis, ever. A window with
          // no readable layer keeps the old size-only classification.
          if let layer = window[kCGWindowLayer as String] as? Int, layer <= 0 {
            continue
          }
          if let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
            let width = bounds["Width"],
            let height = bounds["Height"],
            width > 500 && height > 300
          {
            return .dockOverlay(width: Int(width), height: Int(height))
          }
        }
      }

      if ownerName == "NotificationCenter" {
        return .notificationCenter
      }
    }

    return nil
  }

  /// Both window-server round trips, taken together and off the main actor.
  static func read(dockIsFrontmost: Bool) -> ProactiveCaptureSystemProbe {
    let windowList =
      CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as? [[String: Any]] ?? []
    return ProactiveCaptureSystemProbe(
      specialSystemMode: specialSystemMode(windowList: windowList, dockIsFrontmost: dockIsFrontmost),
      isScreenShareActive: ConferencingApps.activeScreenSharePresent()
    )
  }
}
