import AppKit

/// The last responder in a key-event chain, so an unhandled keystroke ends in silence instead of in
/// `NSBeep()`.
///
/// Typing with no field focused — on Rewind, on Tasks, on the resting Home — sends the key event
/// down the chain: view → window → window controller → `NSApp` → app delegate. When nothing takes
/// it, the last responder's `noResponderFor(_:)` runs, and AppKit's implementation of that beeps for
/// `keyDown`. Nothing else was wrong; the "pop" was purely that the chain had an open end.
///
/// SwiftUI owns the main window, its controller, and the delegate it installs ahead of ours, so the
/// chain cannot be capped by subclassing any of them. Appending one responder after whatever is
/// currently last is the documented seam: SwiftUI's `onKeyPress` handlers, menu key equivalents,
/// and focused controls have all already declined by the time an event reaches here, so absorbing
/// it takes nothing from them. Plain AppKit windows (Feedback, the prompt editors, the onboarding
/// cinematic) do not drain into `NSApp` at all — their chain ends at the window or its controller —
/// so `installEverywhere` also caps each window as it becomes key. (`FloatingControlBarWindow`
/// additionally absorbs in its own `keyDown`, since it acts on Escape and Tab itself.)
///
/// Absorbing is the floor. A key that is *typing* is first offered to `StrayTypingRouter`, which
/// puts it in the field the page means — the search bar, or Chat's composer — so the first letter
/// you type on a page is the first letter of your search rather than a silent miss.
final class UnhandledKeystrokeSink: NSResponder {
  private let router: StrayTypingRouter

  init(router: StrayTypingRouter = .shared) {
    self.router = router
    super.init()
  }

  required init?(coder: NSCoder) { nil }

  /// Route it if it is typing; otherwise swallow it. `super` would forward to a `nil` next responder
  /// and beep, so neither branch calls it.
  override func keyDown(with event: NSEvent) {
    _ = router.route(event)
  }

  /// `nextResponder` is an unretained reference, so the chain does not keep a sink alive; this does.
  @MainActor private static var installed: [UnhandledKeystrokeSink] = []
  @MainActor private static var keyWindowObserver: NSObjectProtocol?

  /// Appends a sink after the last responder reachable from `root`. Idempotent: a chain that already
  /// ends in a sink is left alone.
  @MainActor
  static func install(after root: NSResponder) {
    var last = root
    while let next = last.nextResponder { last = next }
    guard !(last is UnhandledKeystrokeSink) else { return }
    let sink = UnhandledKeystrokeSink()
    last.nextResponder = sink
    installed.append(sink)
  }

  /// Caps the application chain now, and every window's chain as it becomes key. A window whose
  /// chain already drains into the capped application chain (SwiftUI's) is a no-op; a window whose
  /// chain ends at itself or its controller gets its own cap. Re-run on each key change because
  /// AppKit resets a window's `nextResponder` when a controller is assigned.
  @MainActor
  static func installEverywhere() {
    install(after: NSApp)
    guard keyWindowObserver == nil else { return }
    keyWindowObserver = NotificationCenter.default.addObserver(
      forName: NSWindow.didBecomeKeyNotification, object: nil, queue: .main
    ) { note in
      // The notification's object crosses into the main-actor closure boxed, the same way
      // `DesktopAutomationWindowPresentation` carries it; `.main` queue delivery makes this sound.
      let box = KeyWindowBox(value: note.object)
      MainActor.assumeIsolated {
        guard let window = box.value as? NSWindow else { return }
        install(after: window)
      }
    }
  }
}

private struct KeyWindowBox: @unchecked Sendable {
  let value: Any?
}
