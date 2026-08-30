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
///
/// One observer, several listeners: form assist and message-draft assist both want these
/// exact moments, and macOS charges per AXObserver, not per interested party. Subscribers
/// are keyed so each surface can leave without tearing the watcher out from under the
/// others; the machinery runs only while someone is subscribed.
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
  private var subscribers: [String: (FormScanReason) -> Void] = [:]
  /// Called on the raw event, ahead of the debounce. Presenting a card has to wait for a
  /// page to settle; taking one away does not, and a card left over a tab the user has
  /// already left is the one thing this must never do.
  private var immediateSubscribers: [String: () -> Void] = [:]

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

  func subscribe(_ id: String, onScan: @escaping (FormScanReason) -> Void) {
    let wasIdle = isIdle
    subscribers[id] = onScan
    guard wasIdle else { return }
    startMachinery()
  }

  /// Watch the same events without the debounce. Used to retire a card the moment its
  /// context goes away; never to put one up.
  func subscribeImmediate(_ id: String, onEvent: @escaping () -> Void) {
    let wasIdle = isIdle
    immediateSubscribers[id] = onEvent
    guard wasIdle else { return }
    startMachinery()
  }

  func unsubscribeImmediate(_ id: String) {
    immediateSubscribers[id] = nil
    guard isIdle else { return }
    stopMachinery()
  }

  private var isIdle: Bool { subscribers.isEmpty && immediateSubscribers.isEmpty }

  private func startMachinery() {

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
        FormWatcher.shared.broadcast(.periodic)
      }
    }

    retargetObserver()
  }

  func unsubscribe(_ id: String) {
    subscribers[id] = nil
    guard isIdle else { return }
    stopMachinery()
  }

  private func stopMachinery() {
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

  private func broadcast(_ reason: FormScanReason) {
    for onScan in subscribers.values {
      onScan(reason)
    }
  }

  private func broadcastImmediate() {
    for onEvent in immediateSubscribers.values {
      onEvent()
    }
  }

  private func handleAppActivation() {
    retargetObserver()
    broadcastImmediate()
    // An app switch is the strongest signal there is; it skips the debounce so the card
    // for a form the user just came back to is not a second late.
    debounceTask?.cancel()
    debounceTask = nil
    broadcast(.appSwitch)
  }

  private func handleAccessibilityEvent() {
    broadcastImmediate()
    debounceTask?.cancel()
    debounceTask = Task { [weak self] in
      try? await Task.sleep(for: Self.debounce)
      guard !Task.isCancelled else { return }
      self?.broadcast(.accessibilityEvent)
    }
  }

  private func retargetObserver() {
    guard let app = NSWorkspace.shared.frontmostApplication else { return }
    let pid = app.processIdentifier
    // On the way in, not when something needs the tree: Electron takes a moment to build
    // one after being asked, and this is the earliest point we know the user is there.
    ElectronAccessibility.requestTree(for: app)
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
