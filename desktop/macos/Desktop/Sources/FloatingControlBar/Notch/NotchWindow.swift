import AppKit
import SwiftUI

/// The per-display notch panel. Non-activating so opening/typing never
/// surfaces the main window or deactivates the user's frontmost app; the
/// window frame is fixed (sized by NotchViewModel) and never animates.
final class NotchWindow: NSPanel {
  /// The bar must never be buried under third-party overlay apps: notch
  /// companions (e.g. Clicky) park windows at .popUpMenu (101) and full-screen
  /// overlays at .screenSaver (1000), so .statusBar (25) lost the notch to
  /// them. Assistive-tech-high (1500) beats every common overlay level while
  /// staying below the system cursor and the screen-lock shield. It also
  /// covers the menu-bar strip, which the notch body must do.
  static let normalLevel = NSWindow.Level(
    rawValue: Int(CGWindowLevelForKey(.assistiveTechHighWindow))
  )

  /// In-process NSMenus (context menus, pickers) render at .popUpMenu (101);
  /// while one is tracking, the panel drops to that level so the notch cannot
  /// occlude its own menus. Depth-counted because nested submenus emit their
  /// own begin/end tracking notifications.
  private var menuTrackingDepth = 0
  /// Notification tokens live in their own bag so removal can happen from the
  /// bag's nonisolated deinit when the window deallocates.
  private final class ObserverBag: @unchecked Sendable {
    var tokens: [NSObjectProtocol] = []
    deinit { tokens.forEach(NotificationCenter.default.removeObserver) }
  }
  private let menuTrackingObservers = ObserverBag()
  /// While a system permission/auth dialog is frontmost, drop below it so the
  /// user can actually see and answer it — at 1500 the notch would otherwise
  /// cover TCC prompts.
  private var yieldsToSystemDialog = false

  /// Escape pressed while the panel has the keyboard.
  var onEscape: (() -> Void)?

  override init(
    contentRect: NSRect,
    styleMask: NSWindow.StyleMask,
    backing: NSWindow.BackingStoreType,
    defer flag: Bool
  ) {
    super.init(contentRect: contentRect, styleMask: styleMask, backing: backing, defer: flag)

    isFloatingPanel = true
    isOpaque = false
    titleVisibility = .hidden
    titlebarAppearsTransparent = true
    backgroundColor = .clear
    isMovable = false
    hasShadow = false
    isReleasedWhenClosed = false
    hidesOnDeactivate = false
    appearance = NSAppearance(named: .vibrantDark)
    level = Self.normalLevel
    collectionBehavior = [
      .fullScreenAuxiliary,
      .stationary,
      .canJoinAllSpaces,
      .ignoresCycle,
    ]
    registerMenuTrackingObservers()
  }

  func setYieldsToSystemDialog(_ yields: Bool) {
    yieldsToSystemDialog = yields
    applySurfaceLevel()
  }

  private func applySurfaceLevel() {
    if menuTrackingDepth > 0 {
      level = .popUpMenu
    } else if yieldsToSystemDialog {
      level = .floating
    } else {
      level = Self.normalLevel
    }
  }

  private func registerMenuTrackingObservers() {
    let center = NotificationCenter.default
    menuTrackingObservers.tokens.append(
      center.addObserver(forName: NSMenu.didBeginTrackingNotification, object: nil, queue: .main) {
        [weak self] _ in
        MainActor.assumeIsolated {
          guard let self else { return }
          self.menuTrackingDepth += 1
          self.applySurfaceLevel()
        }
      })
    menuTrackingObservers.tokens.append(
      center.addObserver(forName: NSMenu.didEndTrackingNotification, object: nil, queue: .main) {
        [weak self] _ in
        MainActor.assumeIsolated {
          guard let self else { return }
          self.menuTrackingDepth = max(0, self.menuTrackingDepth - 1)
          self.applySurfaceLevel()
        }
      })
  }

  /// The panel takes the keyboard only while it's expanded (see
  /// NotchScreenManager.updateMouseMonitors): opening focuses the composer so
  /// you can type straight in; closing hands the keyboard back to your app.
  /// .nonactivatingPanel keeps the underlying app active throughout.
  var keyboardCaptureAllowed = false {
    didSet {
      guard oldValue != keyboardCaptureAllowed else { return }
      if keyboardCaptureAllowed {
        makeKey()
      } else if isKeyWindow {
        // Give up key + first responder so the frontmost app's window
        // reclaims the keyboard (the notch stays on top at its level).
        makeFirstResponder(nil)
        resignKey()
      }
    }
  }
  override var canBecomeKey: Bool { keyboardCaptureAllowed }
  override var canBecomeMain: Bool { false }

  /// SwiftUI's onExitCommand only reaches focused views; the panel-level
  /// fallback guarantees Esc always closes the notch.
  override func keyDown(with event: NSEvent) {
    if event.keyCode == 53 {
      onEscape?()
      return
    }
    super.keyDown(with: event)
  }

  override func cancelOperation(_ sender: Any?) {
    onEscape?()
  }
}

/// The panel never becomes key while closed, so views must accept the first
/// mouse click or taps get swallowed by window activation.
final class NotchHostingView<Content: View>: NSHostingView<Content> {
  override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}
