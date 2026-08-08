import AppKit
import Foundation

private struct AutomationWindowObjectBox: @unchecked Sendable {
  let value: Any?
}

enum DesktopAutomationUIPresentationMode: String, CaseIterable, Sendable {
  case normal
  case quiet
  case interactive
}

/// Pure geometry for the two automation-only window presentations.
enum DesktopAutomationWindowPlacement {
  static let quietPeekSize = NSSize(width: 24, height: 24)
  static let interactiveMargin: CGFloat = 12

  /// Keep a tiny, click-through corner visible so AppKit continues compositing the real window while
  /// the user's desktop stays usable. In-process captures still render the full content view.
  static func quietFrame(
    windowSize: NSSize,
    visibleFrame: NSRect,
    peekSize: NSSize = quietPeekSize
  ) -> NSRect {
    let width = max(1, windowSize.width)
    let height = max(1, windowSize.height)
    let visibleWidth = min(max(1, peekSize.width), min(width, visibleFrame.width))
    let visibleHeight = min(max(1, peekSize.height), min(height, visibleFrame.height))
    return NSRect(
      x: visibleFrame.maxX - visibleWidth,
      y: visibleFrame.minY - height + visibleHeight,
      width: width,
      height: height)
  }

  /// The brief Accessibility lane: fully visible in the least intrusive corner, never centred over
  /// the user's work. Oversized windows are fitted to the display rather than stranded off-screen.
  static func interactiveFrame(
    windowSize: NSSize,
    visibleFrame: NSRect,
    margin: CGFloat = interactiveMargin
  ) -> NSRect {
    let inset = max(0, margin)
    let available = visibleFrame.insetBy(dx: inset, dy: inset)
    let width = min(max(1, windowSize.width), max(1, available.width))
    let height = min(max(1, windowSize.height), max(1, available.height))
    return NSRect(
      x: available.maxX - width,
      y: available.minY,
      width: width,
      height: height)
  }
}

/// Keeps automation-rendered windows out of the user's way without lying to the app about whether
/// those windows are mounted or visible.
///
/// `quiet` is the normal bridge/visual lane: windows stay ordered in, but almost entirely off-screen,
/// dimmed, click-through, and at normal level. `interactive` is a short-lived Accessibility lane that
/// restores real pixels and input in the bottom-right corner. `normal` returns every property and frame
/// captured before automation took ownership, which is also what a Dock click or user summon does.
@MainActor
enum DesktopAutomationWindowPresentation {
  @MainActor private final class Snapshot {
    weak var window: NSWindow?
    let frame: NSRect
    let alphaValue: CGFloat
    let ignoresMouseEvents: Bool
    let hasShadow: Bool
    let level: NSWindow.Level
    let isMovable: Bool
    let isMovableByWindowBackground: Bool
    let wasVisible: Bool

    init(window: NSWindow) {
      self.window = window
      self.frame = window.frame
      self.alphaValue = window.alphaValue
      self.ignoresMouseEvents = window.ignoresMouseEvents
      self.hasShadow = window.hasShadow
      self.level = window.level
      self.isMovable = window.isMovable
      self.isMovableByWindowBackground = window.isMovableByWindowBackground
      self.wasVisible = window.isVisible
    }
  }

  private static var mode = DesktopAutomationLaunchOptions.uiPresentationMode
  private static var snapshots: [ObjectIdentifier: Snapshot] = [:]
  private static var observers: [NSObjectProtocol] = []
  private static var isApplyingPresentation = false

  static var currentMode: DesktopAutomationUIPresentationMode { mode }
  static var isQuiet: Bool { mode == .quiet }

  static func installIfNeeded() {
    guard DesktopAutomationLaunchOptions.isEnabled, observers.isEmpty else { return }
    let center = NotificationCenter.default
    observers.append(
      center.addObserver(forName: NSWindow.didBecomeKeyNotification, object: nil, queue: .main) {
        notification in
        let objectBox = AutomationWindowObjectBox(value: notification.object)
        MainActor.assumeIsolated {
          guard let window = objectBox.value as? NSWindow else { return }
          applyCurrentMode(to: window)
        }
      })
    observers.append(
      center.addObserver(forName: NSWindow.didUpdateNotification, object: nil, queue: .main) {
        notification in
        let objectBox = AutomationWindowObjectBox(value: notification.object)
        MainActor.assumeIsolated {
          guard mode != .normal, let window = objectBox.value as? NSWindow else { return }
          applyCurrentMode(to: window)
        }
      })
    observers.append(
      center.addObserver(forName: NSApplication.didBecomeActiveNotification, object: nil, queue: .main) { _ in
        MainActor.assumeIsolated {
          // Automation helpers occasionally call AppKit APIs that activate as a side effect. A real
          // hotkey, Dock reopen, or menu action calls `revealForUser()` first and changes the mode.
          guard isQuiet else { return }
          NSApp?.deactivate()
        }
      })
  }

  @discardableResult
  static func setMode(
    _ nextMode: DesktopAutomationUIPresentationMode,
    activate: Bool = false
  ) -> DesktopAutomationUIPresentationMode {
    let previous = mode
    mode = nextMode
    pruneSnapshots()

    switch nextMode {
    case .normal:
      restoreSnapshots()
      if activate {
        NSApp?.activate(ignoringOtherApps: true)
        ShellSummon.shellWindow()?.makeKeyAndOrderFront(nil)
      }
    case .quiet:
      applyCurrentModeToVisibleWindows()
      NSApp?.deactivate()
    case .interactive:
      applyCurrentModeToVisibleWindows()
      if activate {
        NSApp?.activate(ignoringOtherApps: true)
        ShellSummon.shellWindow()?.makeKeyAndOrderFront(nil)
      }
    }
    return previous
  }

  /// A real user summon always wins over an automation launch flag.
  @discardableResult
  static func revealForUser() -> Bool {
    guard mode != .normal else { return false }
    setMode(.normal, activate: false)
    return true
  }

  static func applyLaunchMode(to window: NSWindow) {
    installIfNeeded()
    applyCurrentMode(to: window)
  }

  private static func applyCurrentMode(to window: NSWindow) {
    guard isEligible(window), !isApplyingPresentation else { return }
    isApplyingPresentation = true
    defer { isApplyingPresentation = false }
    switch mode {
    case .normal:
      break
    case .quiet:
      applyQuiet(to: window)
    case .interactive:
      applyInteractive(to: window)
    }
  }

  private static func applyCurrentModeToVisibleWindows() {
    guard !isApplyingPresentation else { return }
    for window in eligibleVisibleWindows() {
      applyCurrentMode(to: window)
    }
  }

  private static func applyQuiet(to window: NSWindow) {
    remember(window)
    guard let screen = targetScreen(for: window) else { return }
    window.level = .normal
    window.hasShadow = false
    window.isMovable = false
    window.isMovableByWindowBackground = false
    window.ignoresMouseEvents = true
    window.alphaValue = 0.04
    let targetFrame = DesktopAutomationWindowPlacement.quietFrame(
      windowSize: window.frame.size,
      visibleFrame: screen.visibleFrame)
    if window.frame != targetFrame {
      window.setFrame(targetFrame, display: true, animate: false)
    }
    if !window.isVisible { window.orderFront(nil) }
  }

  private static func applyInteractive(to window: NSWindow) {
    remember(window)
    guard let snapshot = snapshots[ObjectIdentifier(window)],
      let screen = targetScreen(for: window)
    else { return }
    restoreAppearance(snapshot, to: window)
    window.level = .normal
    let targetFrame = DesktopAutomationWindowPlacement.interactiveFrame(
      windowSize: snapshot.frame.size,
      visibleFrame: screen.visibleFrame)
    if window.frame != targetFrame {
      window.setFrame(targetFrame, display: true, animate: false)
    }
    if !window.isVisible { window.orderFront(nil) }
  }

  private static func remember(_ window: NSWindow) {
    let identifier = ObjectIdentifier(window)
    guard snapshots[identifier] == nil else { return }
    snapshots[identifier] = Snapshot(window: window)
  }

  private static func restoreSnapshots() {
    let remembered = Array(snapshots.values)
    snapshots.removeAll()
    for snapshot in remembered {
      guard let window = snapshot.window else { continue }
      restoreAppearance(snapshot, to: window)
      window.setFrame(snapshot.frame, display: true, animate: false)
      if !snapshot.wasVisible {
        window.orderOut(nil)
      }
    }
  }

  private static func restoreAppearance(_ snapshot: Snapshot, to window: NSWindow) {
    window.alphaValue = snapshot.alphaValue
    window.ignoresMouseEvents = snapshot.ignoresMouseEvents
    window.hasShadow = snapshot.hasShadow
    window.level = snapshot.level
    window.isMovable = snapshot.isMovable
    window.isMovableByWindowBackground = snapshot.isMovableByWindowBackground
  }

  private static func pruneSnapshots() {
    snapshots = snapshots.filter { $0.value.window != nil }
  }

  private static func eligibleVisibleWindows() -> [NSWindow] {
    (NSApp?.windows ?? []).filter { $0.isVisible && isEligible($0) }
  }

  private static func isEligible(_ window: NSWindow) -> Bool {
    guard !window.title.hasPrefix("Item-"), window.frame.width > 8, window.frame.height > 8 else {
      return false
    }
    return true
  }

  private static func targetScreen(for window: NSWindow) -> NSScreen? {
    window.screen ?? ActiveDisplay.screen() ?? NSScreen.main ?? NSScreen.screens.first
  }
}
