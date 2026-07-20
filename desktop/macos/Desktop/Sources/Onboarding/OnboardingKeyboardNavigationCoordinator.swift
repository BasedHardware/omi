import AppKit
import Combine

/// Owns the local arrow-key monitor for one mounted onboarding surface.
///
/// The coordinator deliberately has no app-global state. SwiftUI retains it with
/// `@StateObject`, updates the live navigation bindings on every appearance, and
/// tears it down whenever the onboarding surface disappears.
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

  private let monitorHooks: MonitorHooks
  private var monitorToken: MonitorToken?
  private var navigation: Navigation?

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

  /// Installs exactly one monitor for this mounted owner. Calling this again
  /// refreshes the live bindings without stacking a second monitor.
  func mount(_ navigation: Navigation) {
    self.navigation = navigation
    guard monitorToken == nil else { return }
    monitorToken = monitorHooks.install { [weak self] event in
      guard let self else { return event }
      return self.handle(event)
    }.map(MonitorToken.init)
  }

  /// This is intentionally idempotent: completion can tear down eagerly and
  /// SwiftUI disappearance can then converge on the same cleanup safely.
  func unmount() {
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
    guard let navigation, navigation.isActive() else { return event }
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
