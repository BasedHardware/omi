//
//  StrayTypingRouter.swift — a keystroke nobody was listening for lands in the field you meant.
//
//  `UnhandledKeystrokeSink` caps the responder chain so typing with no field focused is silent
//  instead of a beep. Silence is the floor, not the product: on every page of the shell there is one
//  obvious place a typed letter belongs — the search bar across the top of Tasks, Apps, Memories and
//  Rewind, or the chat composer on Chat — and a person who starts typing on a page means that field.
//  Making them click into it first, on a bar that is the only text field in sight, is a step the bar
//  can take for them.
//
//  ## The shape of it
//
//  - A field that wants stray typing registers with the router while it is in a window
//    (`straysTypingHere`). The registration is anchored by a zero-size AppKit view, the same way
//    `EscapeKeyHandler` anchors Escape: it learns its window in `viewDidMoveToWindow`, so a key is
//    only ever aimed at a field **in the window it was typed into**, and it leaves the registry when
//    the view leaves the window or is freed — a closed window cannot leave a stale claim behind.
//  - When several fields share a window, `priority` decides. Chat mounts a search bar and the
//    composer together, and the composer wins, because Chat is the page where typing means "talk to
//    Omi". A modal drawn *inside* the window (`ShellModalScrim`) registers as a blocker above both,
//    so typing over a modal never lights up the bar behind it.
//  - **Nothing is focused ahead of time.** The bar sits with no caret and no focus stroke until the
//    first key arrives. That first key is what claims focus, so the field only ever lights up as the
//    letter appears in it — the cursor shows up because you typed, not before.
//  - The key that arrived is **re-sent** rather than appended to the text. SwiftUI applies the focus
//    claim at the end of the run-loop turn, so the router steps out to the next turn, confirms the
//    caret is now in an editable text view, parks it at the end of whatever is already there, and
//    lets AppKit deliver the same event to the field. Dead keys, input methods and Option-modified
//    characters all work because the field editor interprets the key itself; a string append would
//    have lost every one of them.
//  - **Every key typed while the caret is on its way is queued behind the first**, in order. A local
//    event monitor holds them for the duration, so a fast second letter cannot slip straight into
//    the newly focused field ahead of the first one and come out transposed, and a burst typed into
//    a busy main thread is not thrown away after its first letter.
//  - If the caret never arrives — the page changed underneath, the claim was refused — the queue is
//    dropped silently, which is exactly what the sink did before this existed. A re-sent event that
//    somehow makes it back to the sink is recognised by identity and dropped, so there is no loop.
//
//  ## What counts as typing
//
//  A printable character with no `⌘`/`⌃` on it. Arrows, function keys, Escape, Tab, Return and
//  Delete are not typing, and neither is a bare Space — Tasks uses Space and Return as commands on
//  the selected row, Rewind uses the arrows, and a search field that opens because you tapped Space
//  is a field that opens when you did not mean it. `StrayTypingPolicy` is the whole rule, kept pure
//  so a test can hold it.
//
//  Brand: nothing here draws (INV-UI-1). Focus is claimed through the field's own binding, so the
//  field styles its own focused state exactly as it does when clicked.
//

import AppKit
import SwiftUI

// MARK: - Policy

/// Which key events count as "typing" — the ones a field would want handed to it.
enum StrayTypingPolicy {
  /// A printable character, typed without `⌘` or `⌃`. See the file header for what is excluded and why.
  static func isTyping(
    characters: String?, charactersIgnoringModifiers: String?, modifierFlags: NSEvent.ModifierFlags
  ) -> Bool {
    let flags = modifierFlags.intersection(.deviceIndependentFlagsMask)
    guard flags.isDisjoint(with: [.command, .control]) else { return false }
    if let characters, !characters.isEmpty {
      return characters.unicodeScalars.first.map(isPrintable) ?? false
    }
    // A dead key (`⌥e` before the `e` of `é`) arrives with empty `characters` and the base key in
    // `charactersIgnoringModifiers`. The field editor knows how to compose it; the sink does not.
    guard let base = charactersIgnoringModifiers?.unicodeScalars.first else { return false }
    return isPrintable(base)
  }

  static func isTyping(_ event: NSEvent) -> Bool {
    guard event.type == .keyDown else { return false }
    return isTyping(
      characters: event.characters, charactersIgnoringModifiers: event.charactersIgnoringModifiers,
      modifierFlags: event.modifierFlags)
  }

  /// Whether a key that arrived in `window` may be re-aimed at a field in it. A sheet or any other
  /// child window has its own controls; a stray key there must not light up a bar behind it.
  /// (Modals drawn inside the window are handled by a blocking registration instead — see
  /// `straysTypingBlocked`.)
  @MainActor
  static func windowAcceptsStrays(_ window: NSWindow?) -> Bool {
    guard let window else { return true }  // Synthetic events carry no window.
    return window.sheetParent == nil && window.parent == nil
  }

  private static func isPrintable(_ scalar: Unicode.Scalar) -> Bool {
    if scalar.properties.isWhitespace { return false }
    switch scalar.properties.generalCategory {
    case .control, .format, .privateUse, .unassigned:
      return false  // Function and arrow keys are private-use scalars (U+F700–U+F8FF).
    default:
      return true
    }
  }
}

// MARK: - Router

/// Holds the fields currently willing to take stray typing and hands an unhandled key to the winner.
@MainActor
final class StrayTypingRouter {
  static let shared = StrayTypingRouter()

  /// Which registration wins when more than one shares a window. Chat mounts a search bar and the
  /// composer together; the composer is `.primary`. A modal drawn inside the window is `.blocking`:
  /// it wins, and it takes nothing — the key is swallowed rather than aimed at the bar behind it.
  enum Priority: Comparable {
    case secondary
    case primary
    case blocking
  }

  typealias Claim = @MainActor () -> Void
  typealias Schedule = @MainActor (@escaping @MainActor () -> Void) -> Void
  typealias CaretHolder = @MainActor (NSEvent) -> NSTextView?
  typealias Deliver = @MainActor (NSEvent) -> Void
  /// Installs a key-down monitor that sees every key before the responder chain does; the handler
  /// returns `nil` to swallow a key. Returns the token `RemoveMonitor` takes.
  typealias InstallMonitor = @MainActor (@escaping @MainActor (NSEvent) -> NSEvent?) -> Any?
  typealias RemoveMonitor = @MainActor (Any) -> Void

  private struct Registration {
    let id: UUID
    /// The window the field lives in. `nil` only for synthetic registrations (tests), which match
    /// synthetic events (no window) and nothing else.
    weak var window: NSWindow?
    let hasWindow: Bool
    let priority: Priority
    let claim: Claim
  }

  /// The re-send is retried across this many run-loop turns for the focus claim to land.
  static let deliveryAttempts = 3

  /// Append-only between removals, so array order is registration order; among equal priorities the
  /// most recently registered wins, which is the most recently mounted field.
  private var registrations: [Registration] = []
  /// The keys waiting for the caret, in the order they were typed. Empty when nothing is in flight.
  private var pending: [NSEvent] = []
  /// The window `pending` belongs to; keys held by the monitor are only those aimed at it.
  private weak var pendingWindow: NSWindow?
  private var monitorToken: Any?
  /// The events being handed back to AppKit right now, so the sink recognises one that comes around again.
  private var delivering: [NSEvent] = []

  // Seams. Production wires AppKit; tests wire counters.
  private let schedule: Schedule
  private let caretHolder: CaretHolder
  private let deliver: Deliver
  private let installMonitor: InstallMonitor
  private let removeMonitor: RemoveMonitor

  init(
    schedule: @escaping Schedule = { work in
      DispatchQueue.main.async { MainActor.assumeIsolated { work() } }
    },
    caretHolder: @escaping CaretHolder = { event in
      // Only a field that can take the letter. A selectable read-only text view (a transcript) can
      // hold first responder too, and it would consume the re-sent key without showing it anywhere.
      guard let textView = (event.window ?? NSApp.keyWindow)?.firstResponder as? NSTextView,
        textView.isEditable
      else { return nil }
      return textView
    },
    deliver: @escaping Deliver = { event in (event.window ?? NSApp.keyWindow)?.sendEvent(event) },
    installMonitor: @escaping InstallMonitor = { handler in
      NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in handler(event) }
    },
    removeMonitor: @escaping RemoveMonitor = { NSEvent.removeMonitor($0) }
  ) {
    self.schedule = schedule
    self.caretHolder = caretHolder
    self.deliver = deliver
    self.installMonitor = installMonitor
    self.removeMonitor = removeMonitor
  }

  /// Offers a field in `window` for stray typing until `unregister`. `claim` must put the caret in
  /// the field. A `.blocking` registration's claim is never run.
  @discardableResult
  func register(window: NSWindow?, priority: Priority, claim: @escaping Claim = {}) -> UUID {
    let registration = Registration(
      id: UUID(), window: window, hasWindow: window != nil, priority: priority, claim: claim)
    registrations.append(registration)
    return registration.id
  }

  func unregister(_ id: UUID) {
    registrations.removeAll { $0.id == id }
  }

  private func target(for window: NSWindow?) -> Registration? {
    let candidates = registrations.filter { registration in
      if registration.hasWindow { return registration.window === window }
      return window == nil
    }
    guard let top = candidates.map(\.priority).max() else { return nil }
    return candidates.last { $0.priority == top }
  }

  /// Takes a key nothing else handled. `true` means a field claimed it and it will be re-sent once
  /// the caret is there; `false` means it is not typing, or there is nowhere for it to go — the
  /// caller swallows it either way.
  func route(_ event: NSEvent) -> Bool {
    if delivering.contains(where: { $0 === event }) { return false }
    guard StrayTypingPolicy.isTyping(event), StrayTypingPolicy.windowAcceptsStrays(event.window)
    else { return false }
    if !pending.isEmpty {
      // The monitor normally holds these; one that reached the chain anyway still belongs in order.
      guard event.window === pendingWindow else { return false }
      pending.append(event)
      return true
    }
    guard let target = target(for: event.window), target.priority != .blocking else { return false }
    target.claim()
    pending = [event]
    pendingWindow = event.window
    holdFollowingKeys()
    attemptDelivery(attemptsLeft: Self.deliveryAttempts)
    return true
  }

  /// While the caret is on its way, every typing key aimed at the same window queues behind the first
  /// instead of racing it into the field.
  private func holdFollowingKeys() {
    monitorToken = installMonitor { [weak self] event in
      guard let self, !self.pending.isEmpty, event.window === self.pendingWindow,
        StrayTypingPolicy.isTyping(event)
      else { return event }
      self.pending.append(event)
      return nil
    }
  }

  private func releaseFollowingKeys() {
    if let monitorToken { removeMonitor(monitorToken) }
    monitorToken = nil
  }

  private func attemptDelivery(attemptsLeft: Int) {
    schedule { [weak self] in
      guard let self, let first = self.pending.first else { return }
      guard let textView = self.caretHolder(first) else {
        if attemptsLeft > 1 {
          self.attemptDelivery(attemptsLeft: attemptsLeft - 1)
        } else {
          self.releaseFollowingKeys()
          self.pending.removeAll()
        }
        return
      }
      self.releaseFollowingKeys()
      let queued = self.pending
      self.pending.removeAll()
      // Becoming first responder selects the field's whole text; a re-sent letter would replace a
      // search you had already typed. Continue it instead.
      let end = (textView.string as NSString).length
      textView.setSelectedRange(NSRange(location: end, length: 0))
      self.delivering = queued
      for event in queued { self.deliver(event) }
      self.delivering.removeAll()
    }
  }
}

// MARK: - SwiftUI seam

extension View {
  /// Typing with nothing focused lands in this control. Registered while the view is in a window; the
  /// first stray key runs `claim`, which must put the caret in the control, and is then re-sent to it.
  func straysTypingHere(
    priority: StrayTypingRouter.Priority = .secondary, claim: @escaping StrayTypingRouter.Claim
  ) -> some View {
    background(StrayTypingAnchor(priority: priority, claim: claim))
  }

  /// `straysTypingHere` for a control focused through a `FocusState` binding.
  func straysTypingHere(
    _ focus: FocusState<Bool>.Binding, priority: StrayTypingRouter.Priority = .secondary
  ) -> some View {
    straysTypingHere(priority: priority) { focus.wrappedValue = true }
  }

  /// While this view is in a window, stray typing in that window goes nowhere. For modals drawn inside
  /// the window, whose controls are the only ones a key should reach.
  func straysTypingBlocked() -> some View {
    background(StrayTypingAnchor(priority: .blocking, claim: {}))
  }
}

/// A zero-size, untouchable view whose only job is to know which window it is in.
private struct StrayTypingAnchor: NSViewRepresentable {
  let priority: StrayTypingRouter.Priority
  let claim: StrayTypingRouter.Claim

  func makeNSView(context: Context) -> StrayTypingAnchorView {
    let view = StrayTypingAnchorView()
    view.priority = priority
    view.claim = claim
    return view
  }

  func updateNSView(_ nsView: StrayTypingAnchorView, context: Context) {
    nsView.priority = priority
    nsView.claim = claim
  }
}

@MainActor
final class StrayTypingAnchorView: NSView {
  var priority: StrayTypingRouter.Priority = .secondary
  var claim: StrayTypingRouter.Claim = {}
  private var registration: UUID?

  override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    removeRegistration()
    guard let window else { return }
    registration = StrayTypingRouter.shared.register(window: window, priority: priority) { [weak self] in
      self?.claim()
    }
  }

  override func hitTest(_ point: NSPoint) -> NSView? { nil }
  override var acceptsFirstResponder: Bool { false }

  private func removeRegistration() {
    if let registration { StrayTypingRouter.shared.unregister(registration) }
    registration = nil
  }

  deinit {
    if let registration {
      Task { @MainActor in StrayTypingRouter.shared.unregister(registration) }
    }
  }
}
