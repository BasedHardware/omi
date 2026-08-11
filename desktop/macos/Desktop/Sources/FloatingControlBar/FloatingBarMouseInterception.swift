import AppKit
import Combine

enum FloatingBarMouseInterceptionPolicy {
  static func shouldIgnoreMouseEvents(
    mouseLocation: NSPoint,
    windowFrame: NSRect,
    isVisible: Bool,
    acceptsMouseHit: (NSPoint) -> Bool
  ) -> Bool {
    guard isVisible, windowFrame.contains(mouseLocation) else { return true }
    let local = NSPoint(
      x: mouseLocation.x - windowFrame.minX,
      y: mouseLocation.y - windowFrame.minY)
    return !acceptsMouseHit(local)
  }
}

@MainActor
final class FloatingBarMouseInterceptionReconciler {
  private nonisolated(unsafe) var monitors: [Any] = []
  private var cancellables = Set<AnyCancellable>()

  init(state: FloatingControlBarState, reconcile: @escaping @MainActor @Sendable () -> Void) {
    let scheduleReconciliation: @Sendable () -> Void = {
      DispatchQueue.main.async { reconcile() }
    }
    if let global = NSEvent.addGlobalMonitorForEvents(
      matching: [.mouseMoved, .leftMouseDragged],
      handler: { _ in scheduleReconciliation() })
    {
      monitors.append(global)
    }
    if let local = NSEvent.addLocalMonitorForEvents(
      matching: [.mouseMoved],
      handler: { event in
        scheduleReconciliation()
        return event
      })
    {
      monitors.append(local)
    }

    // Monitor delivery is not the correctness boundary for a top-level transparent panel.
    // Polling also reconciles a stationary pointer after frame or state transitions.
    Timer.publish(every: 1.0 / 30.0, on: .main, in: .common)
      .autoconnect()
      .sink { _ in reconcile() }
      .store(in: &cancellables)

    let ownershipPublishers: [AnyPublisher<Void, Never>] = [
      state.$showingAIConversation.map { _ in () }.eraseToAnyPublisher(),
      state.$showingAIResponse.map { _ in () }.eraseToAnyPublisher(),
      state.$currentNotification.map { _ in () }.eraseToAnyPublisher(),
      state.$inputViewHeight.map { _ in () }.eraseToAnyPublisher(),
      state.$notchHoverMenuOpen.map { _ in () }.eraseToAnyPublisher(),
    ]
    Publishers.MergeMany(ownershipPublishers)
      .sink { scheduleReconciliation() }
      .store(in: &cancellables)
  }

  deinit {
    monitors.forEach(NSEvent.removeMonitor)
  }
}

extension FloatingControlBarWindow {
  func syncMouseInterception(mouseLocation: NSPoint = NSEvent.mouseLocation) {
    let shouldIgnore = FloatingBarMouseInterceptionPolicy.shouldIgnoreMouseEvents(
      mouseLocation: mouseLocation,
      windowFrame: frame,
      isVisible: isVisible,
      acceptsMouseHit: acceptsMouseHit(inContentPoint:))
    if ignoresMouseEvents != shouldIgnore {
      ignoresMouseEvents = shouldIgnore
    }
  }

  func installMouseInterceptionSync() {
    mouseInterceptionReconciler = FloatingBarMouseInterceptionReconciler(
      state: state,
      reconcile: { [weak self] in self?.syncMouseInterception() })
    syncMouseInterception()
  }
}
