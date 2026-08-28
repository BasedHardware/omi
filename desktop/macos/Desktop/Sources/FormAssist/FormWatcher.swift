import AppKit
import ApplicationServices
import Foundation

/// Why a scan was asked for. The distinction is the cost control: something actually
/// happened on screen, versus the periodic safety net that must not re-walk a window it
/// has already found nothing in.
enum FormScanReason: String, Sendable {
  case appSwitch
  case accessibilityEvent
  case periodic
}

/// Watches for the moment a form appears in front of the user.
///
/// Deliberately independent of the screen-capture pipeline. Form assist used to ride
/// context switches derived from captured frames, which meant it inherited every reason
/// capture can be quiet — a gated tick, an idle machine, a page whose pixels never change
/// — and it could only ever notice a form when the *window title* changed. A single-page
/// application that swaps a job listing for its application form changes neither.
///
/// Accessibility notifications carry exactly the events that matter (focus moved into a
/// field, a web area finished loading, the layout changed) and cost nothing while the
/// screen is still. The periodic pass is the net under them: notification support varies
/// by app, so nothing here is allowed to be the only way a form is found.
@MainActor
final class FormWatcher {
  static let shared = FormWatcher()

  /// Coalesces the burst of notifications a page load emits into one scan.
  static let debounce: Duration = .seconds(1)
  /// The safety net's period. Also how quickly a card notices the user has left.
  static let sweepInterval: TimeInterval = 5

  private var observer: AXObserver?
  private var observedPID: pid_t?
  private var debounceTask: Task<Void, Never>?
  private var sweepTimer: Timer?
  private var activationObserver: (any NSObjectProtocol)?
  private var onScan: ((FormScanReason) -> Void)?

  /// Registered on the application element, which is where an app posts events for its
  /// whole tree. Apps implement different subsets; a rejected registration is normal and
  /// costs nothing, which is why the list is broad rather than minimal.
  private static let notifications: [String] = [
    kAXFocusedUIElementChangedNotification as String,
    kAXFocusedWindowChangedNotification as String,
    kAXWindowCreatedNotification as String,
    kAXTitleChangedNotification as String,
    "AXLoadComplete",
    "AXLayoutChanged",
  ]

  private init() {}

  func start(onScan: @escaping (FormScanReason) -> Void) {
    guard self.onScan == nil else { return }
    self.onScan = onScan

    activationObserver = NSWorkspace.shared.notificationCenter.addObserver(
      forName: NSWorkspace.didActivateApplicationNotification,
      object: nil,
      queue: .main
    ) { _ in
      MainActor.assumeIsolated {
        FormWatcher.shared.handleAppActivation()
      }
    }

    sweepTimer = Timer.scheduledTimer(withTimeInterval: Self.sweepInterval, repeats: true) { _ in
      MainActor.assumeIsolated {
        FormWatcher.shared.onScan?(.periodic)
      }
    }

    retargetObserver()
  }

  func stop() {
    onScan = nil
    debounceTask?.cancel()
    debounceTask = nil
    sweepTimer?.invalidate()
    sweepTimer = nil
    if let activationObserver {
      NSWorkspace.shared.notificationCenter.removeObserver(activationObserver)
    }
    activationObserver = nil
    tearDownObserver()
  }

  private func handleAppActivation() {
    retargetObserver()
    // An app switch is the strongest signal there is; it skips the debounce so the card
    // for a form the user just came back to is not a second late.
    debounceTask?.cancel()
    debounceTask = nil
    onScan?(.appSwitch)
  }

  private func handleAccessibilityEvent() {
    debounceTask?.cancel()
    debounceTask = Task { [weak self] in
      try? await Task.sleep(for: Self.debounce)
      guard !Task.isCancelled else { return }
      self?.onScan?(.accessibilityEvent)
    }
  }

  private func retargetObserver() {
    guard let app = NSWorkspace.shared.frontmostApplication else { return }
    let pid = app.processIdentifier
    guard pid != observedPID else { return }
    guard pid != ProcessInfo.processInfo.processIdentifier else {
      tearDownObserver()
      return
    }

    tearDownObserver()
    guard AXIsProcessTrusted() else { return }

    var created: AXObserver?
    let callback: AXObserverCallback = { _, _, _, _ in
      MainActor.assumeIsolated {
        FormWatcher.shared.handleAccessibilityEvent()
      }
    }
    guard AXObserverCreate(pid, callback, &created) == .success, let created else { return }

    let appElement = AXUIElementCreateApplication(pid)
    for notification in Self.notifications {
      _ = AXObserverAddNotification(created, appElement, notification as CFString, nil)
    }
    CFRunLoopAddSource(
      CFRunLoopGetMain(), AXObserverGetRunLoopSource(created), .defaultMode)

    observer = created
    observedPID = pid
  }

  private func tearDownObserver() {
    if let observer {
      CFRunLoopRemoveSource(
        CFRunLoopGetMain(), AXObserverGetRunLoopSource(observer), .defaultMode)
    }
    observer = nil
    observedPID = nil
  }
}
