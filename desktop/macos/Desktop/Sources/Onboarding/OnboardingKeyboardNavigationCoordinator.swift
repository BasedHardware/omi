import AppKit
import Combine

/// Owns the local arrow-key monitor for the stable parent of the mounted onboarding surface.
@MainActor
final class OnboardingKeyboardNavigationCoordinator: ObservableObject {
  /// AppKit deliberately types monitor tokens as `Any`. These wrappers keep
  /// that framework detail confined while allowing deterministic main-actor
  /// cleanup from `deinit` under strict concurrency.
  private final class MonitorToken: @unchecked Sendable {
    let value: Any

    init(_ value: Any) {
      self.value = value
    }
  }

  private final class MonitorHooks: @unchecked Sendable {
    let install: EventMonitorInstaller
    let remove: EventMonitorRemover

    init(install: @escaping EventMonitorInstaller, remove: @escaping EventMonitorRemover) {
      self.install = install
      self.remove = remove
    }
  }

  typealias EventHandler = (NSEvent) -> NSEvent?
  typealias EventMonitorInstaller = (@escaping EventHandler) -> Any?
  typealias EventMonitorRemover = (Any) -> Void

  struct Navigation {
    let isActive: () -> Bool
    let focusedControlOwnsArrows: () -> Bool
    let currentStep: () -> Int
    let furthestStep: () -> Int
    let apply: (OnboardingFlow.ArrowNavigation) -> Bool
  }

  struct MountLease: Equatable {
    fileprivate let generation: UInt64
  }

  private let monitorHooks: MonitorHooks
  private var monitorToken: MonitorToken?
  private var navigation: (lease: MountLease, value: Navigation)?
  private var nextGeneration: UInt64 = 0

  init(
    installMonitor: @escaping EventMonitorInstaller = { handler in
      NSEvent.addLocalMonitorForEvents(matching: .keyDown, handler: handler)
    },
    removeMonitor: @escaping EventMonitorRemover = { token in
      NSEvent.removeMonitor(token)
    }
  ) {
    monitorHooks = MonitorHooks(install: installMonitor, remove: removeMonitor)
  }

  /// Replaces the active child navigation atomically without stacking monitors.
  /// A delayed disappearance can release only its own lease.
  func mount(_ navigation: Navigation) -> MountLease {
    nextGeneration &+= 1
    let lease = MountLease(generation: nextGeneration)
    self.navigation = (lease, navigation)
    guard monitorToken == nil else { return lease }
    monitorToken = monitorHooks.install { [weak self] event in
      guard let self else { return event }
      return self.handle(event)
    }.map(MonitorToken.init)
    return lease
  }

  /// Tears down only the active child's navigation. Stale child disappearance
  /// is deliberately ignored after a replacement has acquired a newer lease.
  func unmount(_ lease: MountLease?) {
    guard let lease, navigation?.lease == lease else { return }
    navigation = nil
    guard let monitorToken else { return }
    monitorHooks.remove(monitorToken.value)
    self.monitorToken = nil
  }

  deinit {
    if let monitorToken {
      monitorHooks.remove(monitorToken.value)
    }
  }

  private func handle(_ event: NSEvent) -> NSEvent? {
    guard let navigation = navigation?.value, navigation.isActive() else { return event }
    // Repeats are passed through deliberately: holding an arrow never races
    // through skippable onboarding pages.
    guard !event.isARepeat else { return event }
    let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
    guard modifiers.subtracting([.function, .numericPad]).isEmpty else { return event }
    guard !navigation.focusedControlOwnsArrows() else { return event }
    guard
      let action = OnboardingFlow.arrowNavigation(
        keyCode: event.keyCode,
        step: navigation.currentStep(),
        furthestStep: navigation.furthestStep()
      )
    else {
      return event
    }
    return navigation.apply(action) ? nil : event
  }
}

@MainActor
enum OnboardingKeyboardResponderPolicy {
  static func ownsArrows(in window: NSWindow?) -> Bool {
    guard let window else { return false }
    if window is FloatingControlBarWindow { return true }
    return ownsArrows(firstResponder: window.firstResponder)
  }

  static func ownsArrows(firstResponder: NSResponder?) -> Bool {
    var responder = firstResponder
    while let current = responder {
      if current is NSText || current is NSTextView { return true }
      if let textField = current as? NSTextField, textField.isEditable { return true }
      if let comboBox = current as? NSComboBox, comboBox.isEditable { return true }
      if current is NSSegmentedControl || current is NSSlider || current is NSStepper
        || current is NSScroller || current is NSTableView || current is NSOutlineView
        || current is NSCollectionView
      {
        return true
      }
      let next = current.nextResponder
      guard next !== current else { return false }
      responder = next
    }
    return false
  }
}

@MainActor
enum OnboardingDefaultActionPoster {
  static func post(in window: NSWindow?) -> Bool {
    guard let window else { return false }
    let events = [NSEvent.EventType.keyDown, .keyUp].compactMap { phase in
      NSEvent.keyEvent(
        with: phase,
        location: .zero,
        modifierFlags: [],
        timestamp: ProcessInfo.processInfo.systemUptime,
        windowNumber: window.windowNumber,
        context: nil,
        characters: "\r",
        charactersIgnoringModifiers: "\r",
        isARepeat: false,
        keyCode: 36
      )
    }
    guard events.count == 2 else { return false }
    events.forEach { window.postEvent($0, atStart: false) }
    return true
  }
}
