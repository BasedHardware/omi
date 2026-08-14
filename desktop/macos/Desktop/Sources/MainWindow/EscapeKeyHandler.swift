import AppKit
import SwiftUI

/// Maps Esc to a dismiss closure for custom overlay modals. These overlays are
/// ZStack layers, not NSWindow sheets, so AppKit gives them no cancel handling,
/// `onExitCommand` needs focus they never receive, and hidden SwiftUI buttons
/// with a cancel key equivalent get culled from key-equivalent dispatch. A
/// local key-down monitor scoped to the hosting window delivers Esc
/// deterministically. Render it only while its overlay is the topmost modal.
@MainActor
struct OverlayModalEscapeCatcher: View {
  let action: () -> Void

  var body: some View {
    EscapeKeyHandler(priority: .modal) {
      action()
      return true
    }
  }
}

/// Declaration order is the priority order: `dispatchEscape` walks `allCases` **backwards**, so the
/// last case declared gets first refusal and the first case declared is the fallback nobody else
/// wanted.
enum EscapeKeyPriority: Int, CaseIterable {
  /// The window itself. Lowest by construction, because putting the shell away is what Escape means
  /// only when nothing inside it claimed the key — a page navigates Home first (`navigation`), an open
  /// editor cancels first (`editing`), a modal closes first (`modal`). Registered by `ShellSummon`
  /// against the window, not by a view, so no destination can forget to compose it.
  case shell
  case navigation
  case content
  case editing
  case modal
}

@MainActor
struct EscapeKeyHandler: NSViewRepresentable {
  let priority: EscapeKeyPriority
  let action: () -> Bool

  func makeNSView(context: Context) -> EscapeKeyHandlerView {
    let view = EscapeKeyHandlerView()
    view.priority = priority
    view.action = action
    return view
  }

  func updateNSView(_ nsView: EscapeKeyHandlerView, context: Context) {
    nsView.priority = priority
    nsView.action = action
  }
}

@MainActor
final class EscapeKeyHandlerView: NSView {
  var priority: EscapeKeyPriority = .content
  var action: (() -> Bool)?
  private var registration: UUID?

  override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    removeRegistration()
    if let window {
      registration = WindowEscapeKeyMonitor.shared.register(window: window, priority: priority) { [weak self] in
        self?.action?() ?? false
      }
    }
  }

  override func hitTest(_ point: NSPoint) -> NSView? { nil }

  deinit {
    if let registration {
      Task { @MainActor in
        WindowEscapeKeyMonitor.shared.unregister(registration)
      }
    }
  }

  private func removeRegistration() {
    if let registration {
      WindowEscapeKeyMonitor.shared.unregister(registration)
      self.registration = nil
    }
  }
}

@MainActor
final class WindowEscapeKeyMonitor {
  private final class Registration {
    weak var window: NSWindow?
    let priority: EscapeKeyPriority
    let action: () -> Bool

    init(window: NSWindow, priority: EscapeKeyPriority, action: @escaping () -> Bool) {
      self.window = window
      self.priority = priority
      self.action = action
    }
  }

  static let shared = WindowEscapeKeyMonitor()

  private var registrations: [UUID: Registration] = [:]
  private var order: [UUID] = []
  private var monitor: Any?

  private init() {
    monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
      self?.handle(event) ?? event
    }
  }

  func register(window: NSWindow, priority: EscapeKeyPriority = .content, action: @escaping () -> Bool) -> UUID {
    let id = UUID()
    registrations[id] = Registration(window: window, priority: priority, action: action)
    order.append(id)
    return id
  }

  func unregister(_ id: UUID) {
    registrations[id] = nil
    order.removeAll { $0 == id }
  }

  private func handle(_ event: NSEvent) -> NSEvent? {
    guard event.keyCode == 53 else { return event }
    return dispatchEscape(in: event.window) ? nil : event
  }

  func dispatchEscape(in window: NSWindow?) -> Bool {
    for priority in EscapeKeyPriority.allCases.reversed() {
      for id in order.reversed() {
        guard let registration = registrations[id] else { continue }
        guard registration.priority == priority, registration.window === window else { continue }
        if registration.action() { return true }
      }
    }
    return false
  }
}

extension View {
  @MainActor
  func onEscapeKey(priority: EscapeKeyPriority = .content, _ action: @escaping () -> Bool) -> some View {
    overlay { EscapeKeyHandler(priority: priority, action: action) }
  }
}
