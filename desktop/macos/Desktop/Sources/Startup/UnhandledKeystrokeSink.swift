import AppKit

/// The last responder in the application's key-event chain, so an unhandled keystroke ends in
/// silence instead of in `NSBeep()`.
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
/// it takes nothing from them. (Windows with no controller end at themselves and cap their own
/// chain — see `FloatingControlBarWindow.keyDown`.)
final class UnhandledKeystrokeSink: NSResponder {
  /// Swallow it. `super` would forward to a `nil` next responder and beep.
  override func keyDown(with event: NSEvent) {}

  /// `nextResponder` is an unretained reference, so the chain does not keep the sink alive; this does.
  @MainActor private static var installed: UnhandledKeystrokeSink?

  /// Appends a sink after the last responder reachable from `root`. Idempotent: a chain that already
  /// ends in a sink is left alone.
  @MainActor
  static func install(after root: NSResponder) {
    var last = root
    while let next = last.nextResponder { last = next }
    guard !(last is UnhandledKeystrokeSink) else { return }
    let sink = UnhandledKeystrokeSink()
    last.nextResponder = sink
    installed = sink
  }
}
