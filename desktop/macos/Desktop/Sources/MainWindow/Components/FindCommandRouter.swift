//
//  FindCommandRouter.swift — ⌘F puts the caret in the search field of the page you are looking at.
//
//  ⌘F used to work on exactly one page (Brain Map, through its own event monitor). Every page with a
//  search field now gets it from the shared field components (`QuerySearchBar`, `OmiSearchField`,
//  Rewind's bar, the Settings sidebar), not page by page.
//
//  The shape follows `EscapeKeyHandler` and `StrayTypingRouter`: a zero-size AppKit anchor registers
//  the field while it is in a window, so ⌘F only ever reaches a field **in the window it was pressed
//  in**, and a page that is not mounted has no registration to answer with. The shell mounts one
//  destination at a time, so "mounted" is "visible"; a hidden ancestor also disqualifies a field.
//
//  `priority` settles overlaps. A page's search is `.page`. A find field that belongs to something
//  opened on top of the page (a transcript's find-in-transcript) registers `.detail` and wins while
//  it is mounted. When nothing in the window claims ⌘F the key passes on untouched, so a detail that
//  handles ⌘F its own way still receives it when the page's search is not registered — the
//  Conversations search bar is hidden while a conversation detail is open for exactly that reason.
//
//  Brand: nothing here draws (INV-UI-1).
//

import AppKit
import SwiftUI

/// Which ⌘F registration wins when several share a window. Declaration order is priority order.
enum FindCommandPriority: Int, Comparable {
  /// The page's own search field.
  case page
  /// A find field on a surface opened over the page (a transcript's find). Beats the page.
  case detail

  static func < (lhs: FindCommandPriority, rhs: FindCommandPriority) -> Bool {
    lhs.rawValue < rhs.rawValue
  }
}

/// Which key events are ⌘F. Pure so a test can hold it.
enum FindCommandPolicy {
  static func isFindCommand(charactersIgnoringModifiers: String?, modifierFlags: NSEvent.ModifierFlags) -> Bool {
    let flags = modifierFlags.intersection([.command, .control, .option, .shift])
    return flags == .command && charactersIgnoringModifiers?.lowercased() == "f"
  }

  static func isFindCommand(_ event: NSEvent) -> Bool {
    guard event.type == .keyDown else { return false }
    return isFindCommand(
      charactersIgnoringModifiers: event.charactersIgnoringModifiers, modifierFlags: event.modifierFlags)
  }
}

/// Holds the fields that answer ⌘F and hands the key to the winner in the window it was pressed in.
@MainActor
final class FindCommandRouter {
  static let shared = FindCommandRouter(installsMonitor: true)

  typealias Claim = @MainActor () -> Void
  typealias Availability = @MainActor () -> Bool

  private struct Registration {
    let id: UUID
    /// `nil` only for synthetic registrations (tests), which match synthetic events and nothing else.
    weak var window: NSWindow?
    let hasWindow: Bool
    let priority: FindCommandPriority
    let isAvailable: Availability
    let claim: Claim
  }

  /// Append-only between removals: among equal priorities the most recently mounted field wins.
  private var registrations: [Registration] = []
  private let installsMonitor: Bool
  private var monitor: Any?

  init(installsMonitor: Bool = false) {
    self.installsMonitor = installsMonitor
  }

  @discardableResult
  func register(
    window: NSWindow?,
    priority: FindCommandPriority = .page,
    isAvailable: @escaping Availability = { true },
    claim: @escaping Claim
  ) -> UUID {
    installMonitorIfNeeded()
    let registration = Registration(
      id: UUID(), window: window, hasWindow: window != nil, priority: priority,
      isAvailable: isAvailable, claim: claim)
    registrations.append(registration)
    return registration.id
  }

  func unregister(_ id: UUID) {
    registrations.removeAll { $0.id == id }
  }

  /// Runs the winning claim for `window`. `false` when no field there answers, so the key passes on.
  @discardableResult
  func dispatchFind(in window: NSWindow?) -> Bool {
    let candidates = registrations.filter { registration in
      let sameWindow = registration.hasWindow ? registration.window === window : window == nil
      return sameWindow && registration.isAvailable()
    }
    guard let top = candidates.map(\.priority).max(),
      let winner = candidates.last(where: { $0.priority == top })
    else { return false }
    winner.claim()
    return true
  }

  private func installMonitorIfNeeded() {
    guard installsMonitor, monitor == nil else { return }
    monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
      guard let self, FindCommandPolicy.isFindCommand(event) else { return event }
      return self.dispatchFind(in: event.window) ? nil : event
    }
  }
}

// MARK: - SwiftUI seam

extension View {
  /// ⌘F in this window puts the caret in this field while it is mounted.
  func focusesOnFind(
    _ focus: FocusState<Bool>.Binding, priority: FindCommandPriority = .page
  ) -> some View {
    onFindCommand(priority: priority) { focus.wrappedValue = true }
  }

  /// ⌘F in this window runs `perform` while this view is mounted and no higher-priority field claims it.
  func onFindCommand(priority: FindCommandPriority = .page, perform: @escaping @MainActor () -> Void) -> some View {
    background(FindCommandAnchor(priority: priority, claim: perform))
  }
}

private struct FindCommandAnchor: NSViewRepresentable {
  let priority: FindCommandPriority
  let claim: FindCommandRouter.Claim

  func makeNSView(context: Context) -> FindCommandAnchorView {
    let view = FindCommandAnchorView()
    view.updatePriority(priority)
    view.claim = claim
    return view
  }

  func updateNSView(_ nsView: FindCommandAnchorView, context: Context) {
    nsView.claim = claim
    nsView.updatePriority(priority)
  }
}

@MainActor
final class FindCommandAnchorView: NSView {
  private(set) var priority: FindCommandPriority = .page
  var claim: FindCommandRouter.Claim = {}
  private var registration: UUID?

  func updatePriority(_ newValue: FindCommandPriority) {
    guard newValue != priority else { return }
    priority = newValue
    reregister()
  }

  override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    reregister()
  }

  override func hitTest(_ point: NSPoint) -> NSView? { nil }
  override var acceptsFirstResponder: Bool { false }

  private func reregister() {
    if let registration { FindCommandRouter.shared.unregister(registration) }
    registration = nil
    guard let window else { return }
    registration = FindCommandRouter.shared.register(
      window: window, priority: priority,
      isAvailable: { [weak self] in self.map { !$0.isHiddenOrHasHiddenAncestor } ?? false },
      claim: { [weak self] in self?.claim() })
  }

  deinit {
    if let registration {
      Task { @MainActor in FindCommandRouter.shared.unregister(registration) }
    }
  }
}
